from db import Database
from create_bot import bot
from helper.helper import log_exception, get_entity_state
from config_data.config import Config, load_config
import aiohttp
from kb import kb

config: Config = load_config()
db = Database(config.db.path)


async def timer():
    try:
        actual_rent = db.get_all_actual_rent()
        if len(actual_rent) > 0:
            for rent in actual_rent:
                try:
                    if rent[12] == 'Резервація':
                        if rent[13] == 0:
                            await bot.send_message(rent[1], 'Ваш резерв знято')
                            db.cancel_rent('Очікування вичерпане', rent[0])
                            db.locker_status('Доступна оренда', rent[3])
                        else:
                            db.valid_until_down(rent[0])
                    elif rent[12] == 'Очікує оплату':
                        if rent[13] == 0:
                            await bot.send_message(rent[1], 'Ваш резерв знято')
                            db.cancel_rent('Очікування вичерпане', rent[0])
                            db.locker_status('Доступна оренда', rent[3])
                        else:
                            db.valid_until_down(rent[0])
                    elif rent[12] == 'Повторний запит':
                        if rent[13] == 1:
                            await bot.send_message(rent[1], 'Ваш резерв знято')
                            db.cancel_rent('Очікування вичерпане', rent[0])
                            db.locker_status('Доступна оренда', rent[3])
                        else:
                            db.valid_until_down(rent[0])
                    elif rent[12] == 'Очікування відкриття':
                        if rent[13] == 1:
                            await bot.send_message(rent[1], 'Розпочато оренду')
                            db.rent_update_status_and_timer('Оренда', int(rent[4])*4, rent[0])
                        else:
                            db.valid_until_down(rent[0])
                    elif rent[12] == 'Оренда':
                        if rent[13] == 20:
                            await bot.send_message(rent[1], '⏳ До кінця оренди залишилось 5 хв')
                            db.valid_until_down(rent[0])
                        elif rent[13] == 1:
                            await bot.send_message(rent[1], '🕒 Час оренди минув\n'
                                                            'Будь ласка, поверніть спорядження до комірки або продовжіть оренду.\n'
                                                            '💳 Автоматично буде нарахована доплата згідно з чинним тарифом\n',
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
