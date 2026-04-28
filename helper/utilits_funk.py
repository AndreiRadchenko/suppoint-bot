from contextlib import suppress
from datetime import datetime
from math import ceil
from zoneinfo import ZoneInfo

from db import Database
from create_bot import bot
from helper.helper import log_exception, get_entity_state
from config_data.config import Config, load_config
import aiohttp
from kb import kb
from text.text import (
    MSG_RESERVATION_CANCELLED, MSG_RENT_STARTED,
    MSG_RENT_5_MIN_LEFT, MSG_RENT_TIME_EXPIRED,
    MSG_SURCHARGE_REMINDER, MSG_MY_RENTS,
)

config: Config = load_config()
db = Database(config.db.path)

# Tracks users with an open my_rent menu: tg_id -> (chat_id, message_id)
my_rent_open: dict[int, tuple[int, int]] = {}


async def timer():
    try:
        actual_rent = db.get_all_actual_rent()
        if len(actual_rent) > 0:
            for rent in actual_rent:
                try:
                    if rent[12] == 'Резервація':
                        if rent[13] == 0:
                            await bot.send_message(rent[1], MSG_RESERVATION_CANCELLED)
                            db.cancel_rent('Очікування вичерпане', rent[0])
                            db.locker_status('Доступна оренда', rent[3])
                        else:
                            db.valid_until_down(rent[0])
                    elif rent[12] == 'Очікує оплату':
                        if rent[13] == 0:
                            await bot.send_message(rent[1], MSG_RESERVATION_CANCELLED)
                            db.cancel_rent('Очікування вичерпане', rent[0])
                            db.locker_status('Доступна оренда', rent[3])
                        else:
                            db.valid_until_down(rent[0])
                    elif rent[12] == 'Повторний запит':
                        if rent[13] == 1:
                            await bot.send_message(rent[1], MSG_RESERVATION_CANCELLED)
                            db.cancel_rent('Очікування вичерпане', rent[0])
                            db.locker_status('Доступна оренда', rent[3])
                        else:
                            db.valid_until_down(rent[0])
                    elif rent[12] == 'Очікування відкриття':
                        if rent[13] == 1:
                            locker = db.get_locker_by_locker_id(rent[3])
                            station = db.get_station_by_id(locker[1]) if locker else None
                            location = (station[2] or "").strip() if station else f"Станція #{locker[1] if locker else '?'}"
                            cell = locker[2] if locker else str(rent[3])
                            await bot.send_message(rent[1], MSG_RENT_STARTED.format(location=location, cell=cell))
                            db.rent_update_status_and_timer('Оренда', int(rent[4])*4, rent[0])
                        else:
                            db.valid_until_down(rent[0])
                    elif rent[12] == 'Оренда':
                        if rent[13] == 20:
                            locker = db.get_locker_by_locker_id(rent[3])
                            station = db.get_station_by_id(locker[1]) if locker else None
                            location = (station[2] or "").strip() if station else f"Станція #{locker[1] if locker else '?'}"
                            cell = locker[2] if locker else str(rent[3])
                            await bot.send_message(rent[1], MSG_RENT_5_MIN_LEFT.format(location=location, cell=cell))
                            db.valid_until_down(rent[0])
                        elif rent[13] == 1:
                            locker = db.get_locker_by_locker_id(rent[3])
                            station = db.get_station_by_id(locker[1]) if locker else None
                            location = (station[2] or "").strip() if station else f"Станція #{locker[1] if locker else '?'}"
                            cell = locker[2] if locker else str(rent[3])
                            await bot.send_message(rent[1], MSG_RENT_TIME_EXPIRED.format(location=location, cell=cell),
                       reply_markup=kb.user_menu)
                            db.valid_until_down(rent[0])
                        else:
                            db.valid_until_down(rent[0])
                except Exception as e:
                    log_exception(e)
        else:
            pass
    except Exception as e:
        log_exception(e)


def _normalize_ha_url(url: str) -> str:
    normalized = (url or '').strip()
    if normalized.startswith("http://") or normalized.startswith("https://"):
        return normalized
    return f"http://{normalized}"


async def _is_ha_reachable(url: str, token: str) -> bool:
    timeout = aiohttp.ClientTimeout(total=4, sock_connect=3, sock_read=3)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{url}/api/", headers=headers) as response:
                return response.status == 200
    except Exception:
        return False


async def _check_station_online(station_id: int) -> bool:
    station = db.get_station_by_id(station_id)
    if not station:
        return False

    ha_url_raw = (station[7] or '').strip()
    ha_token = (station[8] or '').strip()
    if not ha_url_raw or not ha_token:
        return False

    ha_url = _normalize_ha_url(ha_url_raw)
    if not await _is_ha_reachable(ha_url, ha_token):
        return False

    lockers = db.get_lockers_by_station_id(station_id)
    sensor_entity = None
    for locker in lockers:
        # lockers[5] stores door/sensor entity id used in finish-rent checks.
        entity_id = (locker[5] or '').strip() if len(locker) > 5 else ''
        if entity_id:
            sensor_entity = entity_id
            break

    if not sensor_entity:
        return False

    sensor_state = await get_entity_state(sensor_entity, ha_url, ha_token)
    return sensor_state is not None


async def sync_station_activity():
    try:
        stations = db.get_station_admin_list(include_inactive=True)
        if not stations:
            return

        for station in stations:
            station_id = station[0]
            is_online = await _check_station_online(station_id)
            db.update_station_activity(station_id, is_online)
    except Exception as e:
        log_exception(e)


async def send_surcharge_reminders():
    """Send payment reminders to users with unpaid surcharges.

    Schedule: +1h, +3h after the topup transaction was created,
    then daily at the original time-of-day every subsequent day.
    """
    try:
        kyiv = ZoneInfo('Europe/Kyiv')
        now = datetime.now(kyiv)
        today_str = now.strftime('%Y-%m-%d')

        unpaid = db.get_all_unpaid_surcharges()
        for sc in unpaid:
            # sc indices: 0:id 1:tg_id 5:status 6:to_rent
            # new cols:   9:reminder_1h_sent 10:reminder_3h_sent 11:last_daily_reminder_date
            surcharge_id = sc[0]
            tg_id = sc[1]
            to_rent = sc[6]
            reminder_1h_sent = sc[9] if len(sc) > 9 else 0
            reminder_3h_sent = sc[10] if len(sc) > 10 else 0
            last_daily = sc[11] if len(sc) > 11 else None

            tx = db.get_topup_tx_by_surcharge_id(surcharge_id)
            if not tx or not tx[11]:
                # No payment transaction or no checkout link yet — skip.
                continue

            checkout_url = tx[11]
            created_at_raw = tx[15]  # stored as ISO string (UTC)

            try:
                created_at_naive = datetime.fromisoformat(created_at_raw)
                # If the stored value has no timezone info it was saved as UTC.
                if created_at_naive.tzinfo is None:
                    from zoneinfo import ZoneInfo as _ZI
                    import datetime as _dt
                    created_at = created_at_naive.replace(tzinfo=_dt.timezone.utc).astimezone(kyiv)
                else:
                    created_at = created_at_naive.astimezone(kyiv)
            except (ValueError, TypeError):
                continue

            elapsed_hours = (now - created_at).total_seconds() / 3600

            reminder_text = MSG_SURCHARGE_REMINDER.format(to_rent=to_rent, checkout_url=checkout_url)

            if elapsed_hours >= 1 and not reminder_1h_sent:
                with suppress(Exception):
                    await bot.send_message(tg_id, reminder_text, parse_mode='HTML')
                db.mark_reminder_1h(surcharge_id)
            elif elapsed_hours >= 3 and not reminder_3h_sent:
                with suppress(Exception):
                    await bot.send_message(tg_id, reminder_text, parse_mode='HTML')
                db.mark_reminder_3h(surcharge_id)
            elif elapsed_hours >= 24 and last_daily != today_str:
                # Fire at the same time-of-day as the original (allow any minute >= original)
                original_time_of_day = created_at.hour * 60 + created_at.minute
                current_time_of_day = now.hour * 60 + now.minute
                if current_time_of_day >= original_time_of_day:
                    with suppress(Exception):
                        await bot.send_message(tg_id, reminder_text, parse_mode='HTML')
                    db.mark_daily_reminder(surcharge_id, today_str)
    except Exception as e:
        log_exception(e)


async def refresh_my_rent_menus():
    """Scheduler job: edit open my_rent menus with fresh overtime/surcharge info."""
    if not my_rent_open:
        return
    for tg_id, (chat_id, message_id) in list(my_rent_open.items()):
        try:
            rents = db.get_all_my_rent(tg_id)
            if not rents:
                my_rent_open.pop(tg_id, None)
                continue

            # Build items list
            items = []
            for rent in rents:
                locker = db.get_locker_by_locker_id(rent[3])
                if locker:
                    station = db.get_station_by_id(locker[1])
                    station_label = (station[2] or "").strip() if station else f"Станція #{locker[1]}"
                    items.append((rent[0], locker[2], station_label))

            if not items:
                my_rent_open.pop(tg_id, None)
                continue

            # Build overtime lines
            overtime_lines = []
            for rent in rents:
                if rent[12] == 'Оренда' and rent[13] < 0:
                    overtime_min = ceil(abs(rent[13]) * 15 / 60)
                    locker = db.get_locker_by_locker_id(rent[3])
                    locker_name = locker[2] if locker else f"#{rent[3]}"
                    overtime_lines.append(
                        f"⏰ Оренда #{rent[0]} ({locker_name}): перевищено на {overtime_min} хв"
                    )

            # Build surcharge reminder
            surcharge_part = ""
            surcharges = db.get_unpaid_surcharges_by_user(tg_id)
            for sc in surcharges:
                tx = db.get_topup_tx_by_surcharge_id(sc[0])
                if tx and tx[11]:
                    surcharge_part = MSG_SURCHARGE_REMINDER.format(
                        to_rent=sc[6], checkout_url=tx[11]
                    )
                    break

            parts = [MSG_MY_RENTS]
            if overtime_lines:
                parts.append("\n".join(overtime_lines))
            if surcharge_part:
                parts.append(surcharge_part)
            text = "\n\n".join(parts)

            keyboard = kb.my_rent_keyboard(items)
            with suppress(Exception):
                await bot.edit_message_text(
                    text, chat_id=chat_id, message_id=message_id,
                    reply_markup=keyboard, parse_mode='HTML'
                )
        except Exception as e:
            log_exception(e)
