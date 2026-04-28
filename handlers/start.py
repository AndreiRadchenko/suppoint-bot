import asyncio
import requests
from aiogram.fsm.state import default_state
from create_bot import bot
from text.text import (
    MSG_ADMIN_WELCOME, MSG_REGISTER_PROMPT, MSG_USER_WELCOME,
    MSG_RENT_STARTED, MSG_MY_RENTS, MSG_SURCHARGE_REMINDER,
    MSG_SERVICES_INFO, MSG_PRE_REG_INFO, MSG_PRE_REG_PRICE,
    MSG_AUTO_PAYMENT_NOTE, MSG_NO_OPEN_PROBLEMS, MSG_NO_NEW_SURCHARGES,
    MSG_MANUAL_REJECT_DISABLED, MSG_MANUAL_RESEND_DISABLED, MSG_MANUAL_CONFIRM_DISABLED,
    MSG_NO_ACTIVE_RENTS, MSG_NO_RENTS, MSG_HISTORY_EMPTY,
    MSG_CHOOSE_DATE, MSG_CHOOSE_RENT, MSG_ACTIVE_RENTS_TITLE, MSG_NO_ACTIVE_RENTS_ADM,
    MSG_CHOOSE_STATION, MSG_NO_ACTIVE_STATIONS,
    MSG_CHOOSE_STATION_ADM, MSG_NO_ACTIVE_STATIONS_ADM,
    MSG_NO_LOCKER_INFO, MSG_LOCKER_OPENED, MSG_RENT_NOT_ACTIVE,
    MSG_STATIONS_NOT_FOUND, MSG_STATION_MANAGEMENT,
    MSG_PAYMENT_REVIEW_WAIT, MSG_PAYMENT_UPDATED_ADM,
    MSG_PHOTO_NOT_NEEDED, MSG_COMMAND_DISABLED,
    MSG_NO_LINKED_RENTS, MSG_LOCKER_NOT_FOUND, MSG_CHOOSE_ACTION,
    MSG_ALL_RENTS_CLOSED, MSG_NO_LINKED_RENTS_F, MSG_RENTS_TITLE,
    MSG_RENT_NOT_FOUND, MSG_STATION_ACTIVITY_FAIL, MSG_THANKS,
    MSG_STATUS_AVAILABLE, MSG_STATUS_MAINTENANCE,
)
from collections import defaultdict
from aiogram import Router, F
from config_data.config import Config, load_config
from kb import kb
from aiogram.types import InlineKeyboardButton
from helper.helper import clear_messages, log_exception, get_entity_state
import logging
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, StateFilter
from db import Database
from aiogram import Bot
from aiogram.types import BotCommand
from datetime import datetime
from math import ceil
from aiogram.types.input_file import FSInputFile
from helper.utilits_funk import my_rent_open

config: Config = load_config()
db = Database(config.db.path)

router = Router()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ITEMS_PER_PAGE = 10


def _station_label(station_id: int) -> str:
    station = db.get_station_by_id(station_id)
    if not station:
        return f"Станція #{station_id}"

    station_location = (station[2] or "").strip()
    if station_location:
        return station_location
    return f"Станція #{station_id}"


def _my_rent_items(tg_id: int) -> list:
    """Return [(rent_id, locker_name, station_label)] for all active rents of tg_id."""
    rents = db.get_all_my_rent(tg_id)
    items = []
    for rent in rents:
        my_locker = db.get_locker_by_locker_id(rent[3])
        if my_locker:
            items.append((rent[0], my_locker[2], _station_label(my_locker[1])))
    return items


def _overtime_text(tg_id: int) -> str:
    """Return a text block describing overtimed rents, or empty string if none."""
    rents = db.get_all_my_rent(tg_id)
    lines = []
    for rent in rents:
        if rent[12] == 'Оренда' and rent[13] < 0:
            overtime_min = ceil(abs(rent[13]) * 15 / 60)
            locker = db.get_locker_by_locker_id(rent[3])
            locker_name = locker[2] if locker else f"#{rent[3]}"
            lines.append(f"⏰ Оренда #{rent[0]} ({locker_name}): перевищено на {overtime_min} хв")
    return "\n".join(lines)


def _get_surcharge_info(tg_id: int):
    """Return (to_rent, checkout_url) for the first unpaid surcharge with an active payment link, or None."""
    surcharges = db.get_unpaid_surcharges_by_user(tg_id)
    for sc in surcharges:
        tx = db.get_topup_tx_by_surcharge_id(sc[0])
        if tx and tx[11]:
            return (sc[6], tx[11])
    return None


def _build_my_rent_text(tg_id: int) -> str:
    """Build the full text for the my_rent message including overtime and surcharge info."""
    parts = [MSG_MY_RENTS]
    overtime = _overtime_text(tg_id)
    if overtime:
        parts.append(overtime)
    surcharge_info = _get_surcharge_info(tg_id)
    if surcharge_info:
        to_rent, checkout_url = surcharge_info
        parts.append(MSG_SURCHARGE_REMINDER.format(to_rent=to_rent, checkout_url=checkout_url))
    return "\n\n".join(parts)


@router.message(Command("start"))
async def start(message: Message):
    try:
        tg_id = message.from_user.id
        user_exist = db.user_exists(tg_id)
        if tg_id in config.tg_bot.admin_ids:
            await bot.send_message(tg_id, MSG_ADMIN_WELCOME, reply_markup=kb.admin_menu)
        elif user_exist:
            await bot.send_message(tg_id, MSG_USER_WELCOME, reply_markup=kb.user_menu)
        else:
            await bot.send_message(tg_id, MSG_REGISTER_PROMPT, reply_markup=kb.reg_menu)
        await clear_messages(message.chat.id, message.message_id, 15)
    except Exception as e:
        log_exception(e)


@router.callback_query(F.data == "about_rent_not_reg")
async def about_rent_not_reg(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)
        await callback.message.answer(MSG_SERVICES_INFO, reply_markup=kb.pre_reg_info_menu)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)


@router.callback_query(F.data == "pre_reg_info")
async def pre_reg_info(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)
        await callback.message.answer(MSG_PRE_REG_INFO, reply_markup=kb.pre_reg_info_menu, disable_web_page_preview=True)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)


@router.callback_query(F.data == "pre_reg_price")
async def pre_reg_price(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)
        text = MSG_PRE_REG_PRICE
        await callback.message.answer(text, reply_markup=kb.pre_reg_info_menu, disable_web_page_preview=True)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)


@router.callback_query(F.data == "about_rent_reg")
async def about_rent_reg(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)
        await callback.message.answer(MSG_SERVICES_INFO, reply_markup=kb.pre_reg_info_menu)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)


@router.callback_query(F.data == "check_pay")
async def check_pay(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)
        await callback.message.answer(MSG_AUTO_PAYMENT_NOTE, reply_markup=kb.admin_menu)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data == "check_problem")
async def check_problem(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)
        open_problem = db.get_open_problem()

        if len(open_problem) > 0:
            for problem in open_problem:
                text = f'{problem[9]}\n' \
                       f'@{problem[2]} | {problem[3]}\n' \
                       f'{problem[4]}\n' \
                       f'{problem[7]}'

                fix_menu = kb.problem_fix_keyboard(problem[0])
                print(problem[5])
                if problem[5] == 'document':
                    await bot.send_document(callback.from_user.id, problem[6], caption=text, reply_markup=fix_menu)
                elif problem[5] == 'photo':
                    await bot.send_photo(callback.from_user.id, problem[6], caption=text, reply_markup=fix_menu)
                else:
                    await bot.send_message(callback.from_user.id, text, reply_markup=fix_menu)
        else:
            await callback.message.answer(MSG_NO_OPEN_PROBLEMS, reply_markup=kb.admin_menu)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data == "check_surcharge")
async def check_surcharge(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)
        new_surcharge = db.get_new_surcharge()

        print(new_surcharge)

        if len(new_surcharge) > 0:
            for surcharge in new_surcharge:
                text_perlimit = f'{surcharge[5]} | {surcharge[4]}\n'
                all_perlimit_rent = db.all_perlimit_rent(surcharge[1])
                keyboard = kb.surcharge_review_keyboard(
                    [(rent[0], rent[7]) for rent in all_perlimit_rent],
                    surcharge[0]
                )
                if surcharge[2] == "document":
                    await bot.send_document(callback.from_user.id, surcharge[3], caption=text_perlimit,
                                            parse_mode="Markdown", reply_markup=keyboard)
                else:
                    await bot.send_photo(callback.from_user.id, surcharge[3], caption=text_perlimit,
                                         parse_mode="Markdown", reply_markup=keyboard)
        else:
            await callback.message.answer(MSG_NO_NEW_SURCHARGES, reply_markup=kb.admin_menu)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data == "solution_in_process")
async def back_to_main_menu(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)
        await bot.delete_message(callback.from_user.id, callback.message.message_id)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data == "history_rent")
async def check_pay(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)
        all_rent = db.get_all_history(callback.from_user.id)
        if len(all_rent) > 0:
            my_rent_history_text = 'Історія оренд:\n\n'
            for rent in all_rent:
                if rent[7]:
                    total_price = int(rent[5]) + int(rent[7])
                else:
                    total_price = int(rent[5])
                my_rent_history_text += f'{rent[11]} | {rent[14]}хв | {total_price}грн\n\n'

            await callback.message.answer(my_rent_history_text, reply_markup=kb.user_menu)
            await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
        else:
            await callback.message.answer(MSG_HISTORY_EMPTY, reply_markup=kb.user_menu)
            await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data.startswith('rentNot:'))
async def rentNot(call: CallbackQuery):
    try:
        await bot.answer_callback_query(call.id)
        await call.message.answer(MSG_MANUAL_REJECT_DISABLED)
    except Exception as e:
        log_exception(e)


@router.callback_query(F.data.startswith('reSend:'))
async def reSend(call: CallbackQuery):
    try:
        await bot.answer_callback_query(call.id)
        await call.message.answer(MSG_MANUAL_RESEND_DISABLED)
    except Exception as e:
        log_exception(e)


@router.callback_query(F.data.startswith('rentOk:'))
async def rentOk(call: CallbackQuery):
    try:
        await bot.answer_callback_query(call.id)
        await call.message.answer(MSG_MANUAL_CONFIRM_DISABLED)
    except Exception as e:
        log_exception(e)


@router.callback_query(F.data.startswith('fixit:'))
async def fixit(call: CallbackQuery):
    try:
        await bot.answer_callback_query(call.id)
        problem_id = call.data.split(":")[1]
        db.problem_update_status('Вирішено', problem_id)
        await bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception as e:
        log_exception(e)


@router.callback_query(F.data == "my_rent")
async def my_rent(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)

        tg_id = callback.from_user.id
        items = _my_rent_items(tg_id)
        surcharge_info = _get_surcharge_info(tg_id)
        if items:
            keyboard = kb.my_rent_keyboard(items)
            text = _build_my_rent_text(tg_id)
            sent = await bot.send_message(tg_id, text, reply_markup=keyboard, parse_mode='HTML')
            my_rent_open[tg_id] = (callback.message.chat.id, sent.message_id)
        elif surcharge_info:
            to_rent, checkout_url = surcharge_info
            text = MSG_SURCHARGE_REMINDER.format(to_rent=to_rent, checkout_url=checkout_url)
            await bot.send_message(tg_id, text, reply_markup=kb.user_menu, parse_mode='HTML')
            my_rent_open.pop(tg_id, None)
        else:
            await callback.message.answer(MSG_NO_ACTIVE_RENTS, reply_markup=kb.user_menu)
            my_rent_open.pop(tg_id, None)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data == "refresh_my_rent")
async def refresh_my_rent(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)
        tg_id = callback.from_user.id
        items = _my_rent_items(tg_id)
        if items:
            keyboard = kb.my_rent_keyboard(items)
            text = _build_my_rent_text(tg_id)
            await bot.edit_message_text(
                text, chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                reply_markup=keyboard, parse_mode='HTML'
            )
            my_rent_open[tg_id] = (callback.message.chat.id, callback.message.message_id)
        else:
            my_rent_open.pop(tg_id, None)
            await callback.message.answer(MSG_NO_ACTIVE_RENTS, reply_markup=kb.user_menu)
            await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data == "locker_status")
async def locker_status(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)

        active_stations = db.get_all_active_stations()
        if len(active_stations) > 0:
            buttons = []
            for stations in active_stations:
                stations_id = stations[0]
                stations_loc = stations[2]
                station_label = stations_loc if stations_loc else f"Станція #{stations_id}"

                buttons.append([InlineKeyboardButton(
                    text=station_label,
                    callback_data=f"lockerStatus:{stations_id}"
                )])

            buttons.append([InlineKeyboardButton(
                text=f"Назад",
                callback_data="back_to_main_menu"
            )])

            keyboard = kb.make_keyboard(buttons)

            await bot.send_message(callback.from_user.id, MSG_CHOOSE_STATION, reply_markup=keyboard)
        else:
            await callback.message.answer(MSG_NO_ACTIVE_STATIONS, reply_markup=kb.admin_menu)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


def _station_manage_keyboard(station_id: int, is_active: bool, is_visible: bool):
    return kb.station_manage_keyboard(station_id, is_active, is_visible)


@router.callback_query(F.data == "station_management")
async def station_management(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)
        stations = db.get_station_admin_list(include_inactive=True)
        if not stations:
            await callback.message.answer(MSG_STATIONS_NOT_FOUND, reply_markup=kb.admin_menu)
            return

        buttons = []
        for station in stations:
            station_id, _, location, status, is_active, is_visible, sort_order = station
            vis_icon = "👁" if is_visible else "🙈"
            active_icon = "✅" if is_active else "⏸"
            location_label = location if location else f"Станція #{station_id}"
            label = f"{active_icon}{vis_icon} #{station_id} {location_label} ({status})"
            buttons.append([InlineKeyboardButton(text=label, callback_data=f"station_manage:{station_id}")])

        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main_menu")])
        keyboard = kb.make_keyboard(buttons)
        await callback.message.answer(MSG_STATION_MANAGEMENT, reply_markup=keyboard)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)


@router.callback_query(F.data.startswith("station_manage:"))
async def station_manage(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)
        station_id = int(callback.data.split(":")[1])
        station = db.get_station_by_id(station_id)
        if not station:
            await callback.message.answer(MSG_STATIONS_NOT_FOUND, reply_markup=kb.admin_menu)
            return

        is_active = bool(station[4])
        is_visible = bool(station[5])
        sort_order = station[6]
        station_text = (
            f"🏢 Станція #{station[0]}\n"
            f"Локація: {station[2]}\n"
            f"Статус роботи: {station[3]}\n"
            f"Активна: {'так' if is_active else 'ні'}\n"
            f"Видима для клієнтів: {'так' if is_visible else 'ні'}\n"
            f"Порядок: {sort_order}"
        )
        await callback.message.answer(
            station_text,
            reply_markup=_station_manage_keyboard(station_id, is_active, is_visible),
        )
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)


@router.callback_query(F.data.startswith("station_toggle_vis:"))
async def station_toggle_visibility(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)
        _, station_id_raw, visible_raw = callback.data.split(":")
        station_id = int(station_id_raw)
        target_visible = visible_raw == "1"

        ok, message = db.update_station_visibility(station_id, target_visible)
        if not ok:
            await callback.message.answer(f"⚠️ {message}")
            return

        station = db.get_station_by_id(station_id)
        if not station:
            await callback.message.answer(MSG_STATIONS_NOT_FOUND, reply_markup=kb.admin_menu)
            return

        await callback.message.answer(
            f"Видимість станції #{station_id} оновлено: {'видима' if target_visible else 'прихована'}",
            reply_markup=_station_manage_keyboard(station_id, bool(station[4]), bool(station[5])),
        )
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)


@router.callback_query(F.data.startswith("station_toggle_active:"))
async def station_toggle_active(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)
        _, station_id_raw, active_raw = callback.data.split(":")
        station_id = int(station_id_raw)
        target_active = active_raw == "1"

        if not db.update_station_activity(station_id, target_active):
            await callback.message.answer(MSG_STATION_ACTIVITY_FAIL)
            return

        station = db.get_station_by_id(station_id)
        if not station:
            await callback.message.answer(MSG_STATIONS_NOT_FOUND, reply_markup=kb.admin_menu)
            return

        await callback.message.answer(
            f"Активність станції #{station_id} оновлено: {'активна' if target_active else 'неактивна'}",
            reply_markup=_station_manage_keyboard(station_id, bool(station[4]), bool(station[5])),
        )
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)


@router.callback_query(F.data == "rent_by_day")
async def rent_by_day(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)

        tg_id = callback.message.from_user.id
        dates = db.get_rent_dates_by_user()

        if not dates:
            await callback.message.answer(MSG_NO_RENTS, reply_markup=kb.admin_menu)
            await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
            return

        buttons = []
        for date in dates:
            buttons.append([InlineKeyboardButton(
                text=date, callback_data=f"rent_date_{date}"
            )])

        buttons.append([InlineKeyboardButton(
            text=f"Назад",
            callback_data="back_to_main_menu"
        )])

        keyboard = kb.make_keyboard(buttons)

        await callback.message.answer(MSG_CHOOSE_DATE, reply_markup=keyboard)

        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data == "photo_by_rent")
async def rent_by_day(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)
        dates = db.get_rent_dates_by_user()

        if not dates:
            await callback.message.answer(MSG_NO_RENTS, reply_markup=kb.admin_menu)
            await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
            return

        buttons = []
        for date in dates:
            buttons.append([InlineKeyboardButton(
                text=date, callback_data=f"photo_date_{date}"
            )])

        buttons.append([InlineKeyboardButton(
            text=f"Назад",
            callback_data="back_to_main_menu"
        )])

        keyboard = kb.make_keyboard(buttons)

        await callback.message.answer(MSG_CHOOSE_DATE, reply_markup=keyboard)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data.startswith("photo_date_"))
async def show_rents_by_date(callback: CallbackQuery):
    try:
        date = callback.data.replace("photo_date_", "")
        rents = db.get_rents_by_date_and_user(date)

        if not rents:
            await callback.message.answer(f"Оренд за {date} не знайдено.")
            await callback.answer()
            return

        buttons = []
        if len(rents) > 0:
            for rent in rents:
                buttons.append([InlineKeyboardButton(
                    text=f"{rent[0]}|{rent[2]}|{rent[3]}|{rent[11]}", callback_data=f"dock_to_rent_{rent[0]}"
                )])

            buttons.append([InlineKeyboardButton(
                text=f"Назад",
                callback_data="back_to_main_menu"
            )])

            keyboard = kb.make_keyboard(buttons)
            await callback.message.answer(MSG_CHOOSE_RENT, reply_markup=keyboard)

            await callback.answer()
            await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data.startswith("dock_to_rent_"))
async def show_rents_by_date(callback: CallbackQuery):
    try:
        rent_id = callback.data.replace("dock_to_rent_", "")
        rent = db.get_rent_by_id(rent_id)

        sent_any = False

        pay_tipe = rent[9]
        pay_id = rent[10]
        print('pay_tipe', pay_tipe)
        print('pay_id', pay_id)

        if pay_id:
            if pay_tipe == "document":
                await bot.send_document(callback.from_user.id, pay_id, caption=f'Платіж до оренди №{rent_id}',
                                        parse_mode="Markdown")
            else:
                await bot.send_photo(callback.from_user.id, pay_id, caption=f'Платіж до оренди №{rent_id}',
                                     parse_mode="Markdown")
            sent_any = True

        comp_tipe = rent[15]
        comp_id = rent[16]
        print('comp_tipe', comp_tipe)
        print('comp_id', comp_id)

        if comp_id:
            if comp_tipe == "document":
                await bot.send_document(callback.from_user.id, comp_id, caption=f'Комплектація до оренди №{rent_id}',
                                        parse_mode="Markdown")
            else:
                await bot.send_photo(callback.from_user.id, comp_id, caption=f'Комплектація до оренди №{rent_id}',
                                     parse_mode="Markdown")
            sent_any = True

        surcharge = db.get_surcharge_by_rent(rent_id)
        if surcharge and len(surcharge) > 0:
            perlim_tipe = surcharge[2]
            perlim_id = surcharge[3]

            print('perlim_tipe', perlim_tipe)
            print('perlim_id', perlim_id)
            if perlim_id:
                if perlim_tipe == "document":
                    await bot.send_document(callback.from_user.id, perlim_id, caption=f'Доплата до оренди №{rent_id}',
                                            parse_mode="Markdown")
                else:
                    await bot.send_photo(callback.from_user.id, perlim_id, caption=f'Доплата до оренди №{rent_id}',
                                         parse_mode="Markdown")
                sent_any = True

        if not sent_any:
            await callback.message.answer(f"Для оренди №{rent_id} не знайдено збережених документів/фото.")

        await callback.answer()
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")

#
@router.callback_query(F.data.startswith("rent_date_"))
async def show_rents_by_date(callback: CallbackQuery):
    date = callback.data.replace("rent_date_", "")
    rents = db.get_rents_by_date_and_user(date)

    if not rents:
        await callback.message.answer(f"Оренд за {date} не знайдено.")
        await callback.answer()
        return

    chunk_size = 5
    chunks = [rents[i:i + chunk_size] for i in range(0, len(rents), chunk_size)]

    for index, chunk in enumerate(chunks, 1):
        text = f"📅 Оренди за {date} (частина {index}):\n\n"
        for i, row in enumerate(chunk, 1):
            user = db.get_user_by_tg_id(row[1])
            text += (
                f"№{i + (index - 1) * chunk_size} {row[0]}\n"
                f"{user[4]} | @{user[2]} | {row[2]} | {row[3]}\n"
                f"{row[4]} хв | {row[5]} грн | {row[6]}\n"
                f"{row[7]} грн | {row[8]}\n"
                f"{row[12]}\n"
                f"{row[13] * 15 / 60}хв | {int(row[14]) * 15 / 60}хв\n\n"
            )
        await callback.message.answer(text.strip())
    await callback.answer()


@router.callback_query(F.data.startswith('lockerStatus:'))
async def lockerStatus(call: CallbackQuery):
    try:
        await bot.answer_callback_query(call.id)
        stations_id = call.data.split(":")[1]
        lockers = db.get_lockers_by_station_id(stations_id)

        if len(lockers) > 0:
            text = f'Станція №{stations_id}\n\n'
            buttons = []
            for locker in lockers:
                locker_id = locker[0]
                locker_name = locker[2]
                locker_status = locker[3]
                station_label = _station_label(locker[1])
                locker_text = f'ID:{locker_id} | {locker_name} ({station_label}) | {locker_status}'
                callback_data = f"locker_action:{locker_id}"
                buttons.append([InlineKeyboardButton(text=locker_text, callback_data=callback_data)])
            buttons.append([InlineKeyboardButton(text='Назад', callback_data=f'back_to_main_menu')])
            keyboard = kb.make_keyboard(buttons)

            await call.message.answer(text, reply_markup=keyboard)
        else:
            await call.message.answer(MSG_NO_LOCKER_INFO, reply_markup=kb.admin_menu)
        await clear_messages(call.message.chat.id, call.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data == "back_to_main_menu")
async def back_to_main_menu(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)
        tg_id = callback.from_user.id
        my_rent_open.pop(tg_id, None)
        user_exist = db.user_exists(tg_id)
        if tg_id in config.tg_bot.admin_ids:
            await bot.send_message(tg_id, MSG_ADMIN_WELCOME, reply_markup=kb.admin_menu)
        elif user_exist:
            await bot.send_message(tg_id, MSG_USER_WELCOME, reply_markup=kb.user_menu)
        else:
            await bot.send_message(tg_id, MSG_REGISTER_PROMPT, reply_markup=kb.reg_menu)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)

    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data.startswith('openLocker:'))
async def openLocker(call: CallbackQuery):
    try:
        await bot.answer_callback_query(call.id)
        rent_id = call.data.split(":")[1]
        my_rent = db.get_all_my_rent(tg_id=call.from_user.id)

        if len(my_rent) > 0:
            for rent in my_rent:
                locker_id = rent[3]
                locker = db.get_locker_by_locker_id(locker_id)

                if int(rent[0]) == int(rent_id):
                    try:
                        await switch_on_handler(locker_id)
                    except Exception as e:
                        print(f"🚨 Помилка при відкритті комірки: {e}")
                        retry_keyboard = kb.open_locker_retry_keyboard(rent_id)
                        await call.message.answer(
                            "⚠️ Не вдалося відкрити комірку. Перевіряємо з’єднання із системою.\nСпробуйте ще раз.",
                            reply_markup=retry_keyboard
                        )
                        return

                    if rent[12] == 'Очікування відкриття':
                        station = db.get_station_by_id(locker[1]) if locker else None
                        location = (station[2] or "").strip() if station else f"Станція #{locker[1] if locker else '?'}"
                        cell = locker[2] if locker else str(locker_id)
                        await bot.send_message(rent[1], MSG_RENT_STARTED.format(location=location, cell=cell))
                        db.rent_update_status_and_timer('Оренда', int(rent[4]) * 4, rent[0])
                        db.locker_status("Оренда", rent[3])
                    items = _my_rent_items(call.from_user.id)
                    keyboard = kb.my_rent_keyboard(items) if items else kb.user_menu
                    station = db.get_station_by_id(locker[1]) if locker else None
                    location = (station[2] or "").strip() if station else f"Станція #{locker[1] if locker else '?'}"
                    cell = locker[2] if locker else str(locker_id)
                    await call.message.answer(MSG_LOCKER_OPENED.format(location=location, cell=cell), reply_markup=keyboard)
                    asyncio.create_task(delayed_switch_off(locker_id))
        else:
            await call.message.answer(MSG_RENT_NOT_ACTIVE)
        await clear_messages(call.message.chat.id, call.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


# adm_close_rent:
@router.callback_query(F.data.startswith('adm_openLocker:'))
async def adm_openLocker(call: CallbackQuery):
    try:
        await bot.answer_callback_query(call.id)
        locker_id = call.data.split(":")[1]
        await switch_on_handler(locker_id)
        asyncio.create_task(delayed_switch_off(locker_id))
        await clear_messages(call.message.chat.id, call.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data.startswith('adm_reserve:'))
async def adm_reserve(call: CallbackQuery):
    try:
        await bot.answer_callback_query(call.id)
        locker_id = call.data.split(":")[1]
        locker = db.get_locker_by_locker_id(locker_id)
        if locker[3] == 'Обслуговування':
            db.locker_status('Доступна оренда', locker_id)
        else:
            db.locker_status('Обслуговування', locker_id)
        await clear_messages(call.message.chat.id, call.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data.startswith('adm_close_rent:'))
async def adm_close_rent(call: CallbackQuery):
    try:
        await bot.answer_callback_query(call.id)
        locker_id = call.data.split(":")[1]
        db.locker_status('Доступна оренда', locker_id)
        all_rent_by_locker = db.get_all_actual_rent()
        if len(all_rent_by_locker) > 0:
            for rent in all_rent_by_locker:
                print(rent[3])
                print(locker_id)
                print(rent[3] == locker_id)
                if rent[3] == locker_id:
                    db.rent_update_status_and_timer('Завершено адміністратором', 0, rent[0])
                    await call.message.answer(f'Оренда №{rent[0]} завершена')
        else:
            await call.message.answer(MSG_NO_LINKED_RENTS)
        await clear_messages(call.message.chat.id, call.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data.startswith('test:'))
async def adm_reserve(call: CallbackQuery):
    try:
        await bot.answer_callback_query(call.id)
        locker_id = call.data.split(":")[1]
        locker = db.get_locker_by_locker_id(locker_id)
        state1, state2 = await get_locker_states(locker)
        station_label = _station_label(locker[1])
        await call.message.answer(f'Статус для комірки {locker[2]} ({station_label}) ID{locker[0]}:\n'
                                  f'🔓 Замок - {state1}\n'
                                  f'🚪 двері - {state2}')
        await clear_messages(call.message.chat.id, call.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data.startswith('locker_action:'))
async def locker_action(call: CallbackQuery):
    try:
        await bot.answer_callback_query(call.id)
        locker_id = call.data.split(":")[1]
        locker = db.get_locker_by_locker_id(locker_id)
        if not locker:
            await call.message.answer(MSG_LOCKER_NOT_FOUND)
            return
        station_label = _station_label(locker[1])
        keyboard = kb.locker_action_keyboard(locker_id, locker[2], station_label)
        await call.message.answer(MSG_CHOOSE_ACTION, reply_markup=keyboard)
        await bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data.startswith('perlim:'))
async def perlim(call: CallbackQuery):
    try:
        await bot.answer_callback_query(call.id)
        _, rent_id, surcharge_id = call.data.split(":")
        rent = db.get_rent_by_id(rent_id)
        db.rent_update_status_and_timer('Завершено', 0, rent_id)
        db.rent_update_pay_2_status(rent_id)

        db.surcharge_update_status('Враховано', surcharge_id, rent_id)

        await bot.send_message(rent[1], MSG_THANKS,
                               reply_markup=kb.user_menu)

        await bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception as e:
        log_exception(e)


@router.callback_query(F.data.startswith('is_spam:'))
async def is_spam(call: CallbackQuery):
    try:
        await bot.answer_callback_query(call.id)
        _, surcharge_id = call.data.split(":")
        db.surcharge_update_status('Спам', surcharge_id)
        await bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception as e:
        log_exception(e)


@router.message(F.photo | F.document, StateFilter(default_state))
async def get_photo(message: Message):
    try:
        file_type = None
        file_id = None

        if message.photo:
            file_type = "photo"
            file_id = message.photo[-1].file_id
        elif message.document:
            file_type = "document"
            file_id = message.document.file_id

        re_send_rent = db.get_re_send_rent(message.from_user.id)
        if len(re_send_rent) > 0:
            for rent in re_send_rent:
                print(rent)
                db.update_status_and_timer_for_rent(message.from_user.id, rent[2], rent[3],
                                                    'Перевірка оплати', 0, file_type, file_id, 'Повторний запит')

            await message.answer(MSG_PAYMENT_REVIEW_WAIT)
            for admin in config.tg_bot.admin_ids:
                await bot.send_message(admin, MSG_PAYMENT_UPDATED_ADM, reply_markup=kb.admin_menu)
        else:
            await message.answer(MSG_PHOTO_NOT_NEEDED)
    except Exception as e:
        log_exception(e)


@router.message(Command("get_info_1"))
async def start(message: Message):
    try:
        await message.answer(MSG_COMMAND_DISABLED)
    except Exception as e:
        log_exception(e)
        return "Помилка при отриманні стану сутності."


@router.message(Command("get_info_2"))
async def start(message: Message):
    try:
        await message.answer(MSG_COMMAND_DISABLED)
    except Exception as e:
        log_exception(e)


def toggle_switch(state: str, hass_url: str, token: str, entity_id: str) -> bool:
    url = f"{hass_url}/api/services/switch/{state}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {"entity_id": entity_id}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=(3, 5))
        return response.status_code == 200
    except requests.RequestException as e:
        print(f"🚨 HA request error: {e}")
        return False


def _normalize_ha_url(url: str) -> str:
    normalized = (url or '').strip()
    if normalized.startswith("http://") or normalized.startswith("https://"):
        return normalized
    return f"http://{normalized}"


def _station_ha_for_locker(locker_id: int):
    locker = db.get_locker_by_locker_id(locker_id)
    if not locker:
        raise RuntimeError(f"Комірку {locker_id} не знайдено")

    station = db.get_station_by_id(locker[1])
    if not station:
        raise RuntimeError(f"Станцію {locker[1]} не знайдено")

    ha_url = (station[7] or '').strip()
    ha_token = (station[8] or '').strip()
    auto_lock_delay = int(station[9] or 15)
    if not ha_url or not ha_token:
        raise RuntimeError(f"Для станції #{station[0]} не налаштований station-level Home Assistant")

    return _normalize_ha_url(ha_url), ha_token, max(1, auto_lock_delay), locker


async def get_locker_states(locker):
    ha_url, ha_token, _, _ = _station_ha_for_locker(int(locker[0]))
    state1 = await get_entity_state(locker[4], ha_url, ha_token)
    state2 = await get_entity_state(locker[5], ha_url, ha_token)
    return state1, state2


async def switch_on_handler(locker_id: int):
    ha_url, ha_token, _, locker = _station_ha_for_locker(int(locker_id))
    success = await asyncio.to_thread(toggle_switch, "turn_on", ha_url, ha_token, locker[4])
    if success:
        print("✅ Перемикач увімкнено!")
    else:
        raise RuntimeError(f"Не вдалося увімкнути перемикач {locker[4]}")


async def switch_off_handler(locker_id: int):
    ha_url, ha_token, _, locker = _station_ha_for_locker(int(locker_id))
    success = await asyncio.to_thread(toggle_switch, "turn_off", ha_url, ha_token, locker[4])
    if success:
        print("✅ Перемикач вимкнено!")
    else:
        print(f"❌ Не вдалося вимкнути перемикач {locker[4]}.")


async def delayed_switch_off(locker_id: int):
    _, _, delay, _ = _station_ha_for_locker(int(locker_id))
    await asyncio.sleep(delay)
    await switch_off_handler(locker_id)


# f_locker_status

@router.callback_query(F.data == "f_locker_status")
async def f_locker_status(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)

        active_stations = db.get_all_active_stations()
        if len(active_stations) > 0:
            buttons = []
            for stations in active_stations:
                stations_id = stations[0]
                stations_loc = stations[2]
                station_label = stations_loc if stations_loc else f"Станція #{stations_id}"

                buttons.append([InlineKeyboardButton(
                    text=station_label,
                    callback_data=f"f_locker_status:{stations_id}"
                )])

            buttons.append([InlineKeyboardButton(
                text=f"🔙 Назад",
                callback_data="back_to_main_menu"
            )])

            keyboard = kb.make_keyboard(buttons)

            await bot.send_message(callback.from_user.id, MSG_CHOOSE_STATION_ADM, reply_markup=keyboard)
        else:
            await callback.message.answer(MSG_NO_ACTIVE_STATIONS_ADM, reply_markup=kb.admin_menu)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        print(f"🚨 f_locker_status: {e}")


@router.callback_query(F.data.startswith('f_locker_status:'))
async def f_locker_status(call: CallbackQuery):
    try:
        await bot.answer_callback_query(call.id)
        stations_id = call.data.split(":")[1]
        lockers = db.get_lockers_by_station_id(stations_id)

        if len(lockers) > 0:
            text = f'Список комірок станція №{stations_id}\n\n'
            buttons = []
            for locker in lockers:
                locker_id = locker[0]
                locker_name = locker[2]
                locker_status = locker[3]
                kit = db.get_inventory_kit_by_locker_and_station_id(stations_id, locker_id)
                station_label = _station_label(locker[1])
                locker_text = f'{locker_name} ({station_label}) | {kit[1]} | {locker_status}'
                callback_data = f"f_locker_action:{locker_id}"
                buttons.append([InlineKeyboardButton(text=locker_text, callback_data=callback_data)])
            buttons.append([InlineKeyboardButton(text='🔙 Назад', callback_data=f'f_locker_status')])
            keyboard = kb.make_keyboard(buttons)

            await call.message.answer(text, reply_markup=keyboard)
        else:
            await call.message.answer(MSG_NO_LOCKER_INFO, reply_markup=kb.admin_menu)
        await clear_messages(call.message.chat.id, call.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data.startswith('f_locker_action:'))
async def f_locker_action(call: CallbackQuery):
    try:
        await bot.answer_callback_query(call.id)
        locker_id = call.data.split(":")[1]
        locker = db.get_locker_by_locker_id(locker_id)
        kit = db.get_inventory_kit_by_locker_and_station_id(locker[1], locker[0])
        station_label = _station_label(locker[1])

        keyboard = kb.f_locker_action_keyboard(locker_id, locker[1])

        state1, state2 = await get_locker_states(locker)

        locker_text = f'Комірка {locker[2]} ({station_label})\n' \
                      f'Тип: {kit[1]}\n' \
                      f'Статус: {locker[3]}\n' \
                      f'Замок: {state1}\n' \
                      f'Двері: {state2}'

        await call.message.answer(locker_text, reply_markup=keyboard)
        await bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data.startswith('f_adm_openLocker:'))
async def f_adm_openLocker(call: CallbackQuery):
    try:
        await bot.answer_callback_query(call.id)
        locker_id = call.data.split(":")[1]
        locker = db.get_locker_by_locker_id(locker_id)
        await switch_on_handler(locker_id)
        asyncio.create_task(delayed_switch_off(locker_id))

        keyboard = kb.f_locker_action_keyboard(locker_id, locker[1])

        station = db.get_station_by_id(locker[1]) if locker else None
        location = (station[2] or "").strip() if station else f"Станція #{locker[1] if locker else '?'}"
        cell = locker[2] if locker else str(locker_id)
        await call.message.answer(MSG_LOCKER_OPENED.format(location=location, cell=cell), reply_markup=keyboard)
        await clear_messages(call.message.chat.id, call.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data.startswith('f_adm_reserve:'))
async def f_adm_reserve(call: CallbackQuery):
    try:
        await bot.answer_callback_query(call.id)
        locker_id = call.data.split(":")[1]
        locker = db.get_locker_by_locker_id(locker_id)

        keyboard = kb.f_locker_action_keyboard(locker_id, locker[1])

        if locker[3] == 'Обслуговування':
            db.locker_status('Доступна оренда', locker_id)
            await call.message.answer(MSG_STATUS_AVAILABLE, reply_markup=keyboard)
        else:
            db.locker_status('Обслуговування', locker_id)
            await call.message.answer(MSG_STATUS_MAINTENANCE, reply_markup=keyboard)
        await clear_messages(call.message.chat.id, call.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data.startswith('f_adm_close_rent:'))
async def f_adm_close_rent(call: CallbackQuery):
    try:
        await bot.answer_callback_query(call.id)
        locker_id = call.data.split(":")[1]
        locker = db.get_locker_by_locker_id(locker_id)
        db.locker_status('Доступна оренда', locker_id)
        all_rent_by_locker = db.get_all_actual_rent()

        keyboard = kb.f_locker_action_keyboard(locker_id, locker[1])

        if len(all_rent_by_locker) > 0:
            counter = 0
            for rent in all_rent_by_locker:
                print(rent[3] == locker_id)
                if rent[3] == locker_id:
                    counter += 1
                    db.rent_update_status_and_timer('Завершено адміністратором', 0, rent[0])
                    await call.message.answer(f'Оренда №{rent[0]} завершена')
            if counter > 0:
                await call.message.answer(MSG_ALL_RENTS_CLOSED, reply_markup=keyboard)
            else:
                await call.message.answer(MSG_NO_LINKED_RENTS_F, reply_markup=keyboard)
        else:
            await call.message.answer(MSG_NO_LINKED_RENTS_F, reply_markup=keyboard)
        await clear_messages(call.message.chat.id, call.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data == "f_rent")
async def f_rent(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)
        await callback.message.answer(MSG_RENTS_TITLE, reply_markup=kb.f_rent_menu)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)


@router.callback_query(F.data == "active_rents")
async def active_rents(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)
        actual_rent = db.get_all_actual_rent()

        if len(actual_rent) > 0:
            buttons = []
            for rent in actual_rent:
                user_info = db.get_user_by_tg_id(rent[1])
                buttons.append([InlineKeyboardButton(text=f"#{rent[0]} | {user_info[3]} | {rent[12]}",
                                                     callback_data=f"about_actual_rent:{rent[0]}")])
            buttons.append([InlineKeyboardButton(text=f"🔙 Назад", callback_data="f_rent")])
            keyboard = kb.make_keyboard(buttons)
            await callback.message.answer(MSG_ACTIVE_RENTS_TITLE, reply_markup=keyboard)

        else:
            await callback.message.answer(MSG_NO_ACTIVE_RENTS_ADM, reply_markup=kb.f_rent_menu)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)


@router.callback_query(F.data.startswith('about_actual_rent:'))
async def about_actual_rent(call: CallbackQuery):
    try:
        await bot.answer_callback_query(call.id)
        rent_id = call.data.split(":")[1]
        rent = db.get_rent_by_id(rent_id)
        user_info = db.get_user_by_tg_id(rent[1])
        locker = db.get_locker_by_locker_id(rent[3])
        per_limit = db.get_surcharge_by_rent(rent_id)

        rent_time = ''
        if rent[13] < 0:
            rent_time = f"Час оренди перевищено на {int(round(int(rent[13]) * -1 * 15 / 60))}хв"
        else:
            rent_time = f"До кінця оренди залишилось {int(round(int(rent[13]) * 15 / 60))}хв"

        _active_statuses = {'Резервація', 'Очікує оплату', 'Очікування відкриття', 'Оренда', 'Очікує доплату', 'Повторний запит'}
        buttons = []
        if rent[8] == 'NOT':
            sc_id = per_limit[0] if per_limit else 0
            buttons.append([InlineKeyboardButton(text='🚫 Скасувати доплату', callback_data=f'adm_cancel_surcharge:{sc_id}:{rent[0]}')])
        if rent[12] in _active_statuses:
            buttons.append([InlineKeyboardButton(text='🔴 Примусово завершити', callback_data=f'adm_force_close_rent:{rent[0]}')])
        buttons.append([InlineKeyboardButton(text='🔙 Назад', callback_data=f'active_rents')])
        keyboard = kb.make_keyboard(buttons)

        about_actual_rent_text = f"<strong>Деталі оренди #{rent[1]}</strong>\n\n" \
                                 f"Кліент: {user_info[3]}\n" \
                                 f"TGU: @{user_info[2]}\n" \
                                 f"Телефон: {user_info[4]}\n" \
                                 f"Створено: {rent[11]}\n" \
                                 f"Комірка: {locker[2]} ({_station_label(locker[1])}) | {locker[3]}\n" \
                                 f"Статус: {rent[12]}\n" \
                                 f"Час оренди: {rent[4]}хв\n" \
                                 f"Передоплата: {rent[5]}грн | {rent[6]}\n" \
                                 f"Доплата: {rent[7]}грн | {rent[8]}\n" \
                                 f"{rent_time}\n" \
                                 f"Весь час (доступно при доплаті) {rent[14]}хв"

        dock_array = []
        if rent:
            pay_dock = rent[9]
            pay_id = rent[10]
            dock_array.append((pay_dock, pay_id, '📄 Квитанція'))

        if rent:
            com_dock = rent[15]
            com_id = rent[16]
            dock_array.append((com_dock, com_id, '📄 Комплектація'))

        if per_limit:
            per_dock = per_limit[2]
            per_id = per_limit[3]
            dock_array.append((per_dock, per_id, '📄 Доплата'))

        for dock in dock_array:
            print(dock)

            if dock[0] == 'document':
                await bot.send_document(call.from_user.id, document=dock[1], caption=dock[2])
            elif dock[0] == 'photo':
                await bot.send_photo(call.from_user.id, photo=dock[1], caption=dock[2])
            else:
                print(f"⚠️ Невідомий тип файлу")

        await call.message.answer(about_actual_rent_text, reply_markup=keyboard)
        await clear_messages(call.message.chat.id, call.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data.startswith("history_rents"))
async def history_rents(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)
        tg_id = callback.from_user.id

        # Отримуємо всі дати
        dates = db.get_rent_dates_by_user()
        if not dates:
            await callback.message.answer(MSG_NO_RENTS, reply_markup=kb.admin_menu)
            await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
            return

        # Визначаємо сторінку з callback_data (наприклад, history_rents:0)
        parts = callback.data.split(":")
        page = int(parts[1]) if len(parts) > 1 else 0

        # Рахуємо скільки сторінок всього
        total_pages = ceil(len(dates) / ITEMS_PER_PAGE)

        # Відбираємо елементи для поточної сторінки
        start = page * ITEMS_PER_PAGE
        end = start + ITEMS_PER_PAGE
        current_dates = dates[start:end]

        # Створюємо кнопки
        buttons = [
            [InlineKeyboardButton(text=date, callback_data=f"f_rent_date_{date}")]
            for date in current_dates
        ]

        # Кнопки пагінації
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"history_rents:{page-1}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"history_rents:{page+1}"))

        if nav_buttons:
            buttons.append(nav_buttons)

        # Кнопка назад
        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main_menu")])

        # Відправка
        keyboard = kb.make_keyboard(buttons)
        await callback.message.edit_text(MSG_CHOOSE_DATE, reply_markup=keyboard)
    except Exception as e:
        log_exception(e)

@router.callback_query(F.data.startswith('adm_force_close_rent:'))
async def adm_force_close_rent(call: CallbackQuery):
    try:
        await bot.answer_callback_query(call.id)
        rent_id = call.data.split(":")[1]
        rent = db.get_rent_by_id(rent_id)
        if not rent:
            await call.message.answer(MSG_RENT_NOT_FOUND)
            return

        base_time = int(rent[4] or 0)
        timer = int(rent[13] or 0)

        if timer >= 0:
            total_time = base_time
        else:
            overtime_min = abs(timer) / 4
            total = base_time + overtime_min
            total_time = max(15, round(total / 15) * 15)

        db.add_total_time(total_time, rent[0])
        db.rent_update_status_and_timer('Завершено адміністратором', 0, rent[0])
        db.locker_status('Доступна оренда', rent[3])

        # Auto-cancel any unpaid surcharge for this rent.
        per_limit = db.get_surcharge_by_rent(rent[0])
        if per_limit and per_limit[4] == 'Очікує оплату':
            db.cancel_surcharge(per_limit[0])

        await bot.send_message(
            rent[1],
            f"✅ Вашу оренду №{rent[0]} завершено адміністратором.",
            reply_markup=kb.user_menu,
        )
        await call.message.answer(
            f"✅ Оренду №{rent[0]} завершено примусово.\n"
            f"Загальний час: {total_time} хв.\n"
            f"Комірку звільнено.",
            reply_markup=kb.admin_menu,
        )
    except Exception as e:
        log_exception(e)

@router.callback_query(F.data.startswith('adm_cancel_surcharge:'))
async def adm_cancel_surcharge(call: CallbackQuery):
    try:
        await bot.answer_callback_query(call.id)
        _, surcharge_id, rent_id = call.data.split(":")
        rent = db.get_rent_by_id(rent_id)
        if not rent:
            await call.message.answer(MSG_RENT_NOT_FOUND)
            return

        # Cancel surcharge record if one was passed.
        if surcharge_id != '0':
            db.cancel_surcharge(surcharge_id)

        # Always mark pay_2 as settled.
        db.rent_update_pay_2_status(rent_id)

        # Close rent and free locker only if still active.
        _active_statuses = {'Резервація', 'Очікує оплату', 'Очікування відкриття', 'Оренда', 'Очікує доплату', 'Повторний запит'}
        if rent[12] in _active_statuses:
            db.rent_update_status_and_timer('Завершено адміністратором', 0, rent_id)
            db.locker_status('Доступна оренда', rent[3])
            admin_note = "Оренду завершено. Комірку звільнено."
        else:
            admin_note = "Оренда вже завершена."

        await bot.send_message(
            rent[1],
            f"✅ Доплату за вашу оренду №{rent_id} скасовано адміністратором.\n"
            f"Борг погашено автоматично.",
            reply_markup=kb.user_menu,
        )
        await call.message.answer(
            f"✅ Доплату за оренду №{rent_id} скасовано. {admin_note}",
            reply_markup=kb.admin_menu,
        )
    except Exception as e:
        log_exception(e)

@router.callback_query(F.data.startswith("f_rent_date_"))
async def show_rents_by_date(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)
        date = callback.data.replace("f_rent_date_", "")
        rents = db.get_rents_by_date_and_user(date)
        if len(rents) > 0:
            buttons = []
            for rent in rents:
                user_info = db.get_user_by_tg_id(rent[1])
                buttons.append([InlineKeyboardButton(text=f"#{rent[0]} | {user_info[3]} | {rent[12]}",
                                                     callback_data=f"history_element:{rent[0]}")])
            buttons.append([InlineKeyboardButton(text=f"🔙 Назад", callback_data="history_rents")])
            keyboard = kb.make_keyboard(buttons)
            await callback.message.answer(MSG_ACTIVE_RENTS_TITLE, reply_markup=keyboard)

        else:
            await callback.message.answer(MSG_NO_ACTIVE_RENTS_ADM, reply_markup=kb.f_rent_menu)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)


@router.callback_query(F.data.startswith('history_element:'))
async def about_actual_rent(call: CallbackQuery):
    try:
        await bot.answer_callback_query(call.id)
        rent_id = call.data.split(":")[1]
        rent = db.get_rent_by_id(rent_id)
        user_info = db.get_user_by_tg_id(rent[1])
        locker = db.get_locker_by_locker_id(rent[3])
        per_limit = db.get_surcharge_by_rent(rent_id)

        rent_time = ''
        if rent[13] < 0:
            rent_time = f"Час оренди перевищено на {int(round(int(rent[13]) * -1 * 15 / 60))}хв"
        else:
            rent_time = f"До кінця оренди залишилось {int(round(int(rent[13]) * 15 / 60))}хв"

        buttons = []
        if rent[8] == 'NOT':
            sc_id = per_limit[0] if per_limit else 0
            buttons.append([InlineKeyboardButton(text='🚫 Скасувати доплату', callback_data=f'adm_cancel_surcharge:{sc_id}:{rent[0]}')])
        buttons.append([InlineKeyboardButton(text='🔙 Назад', callback_data=f'f_rent')])
        keyboard = kb.make_keyboard(buttons)

        about_actual_rent_text = f"<strong>Деталі оренди #{rent[1]}</strong>\n\n" \
                                 f"Кліент: {user_info[3]}\n" \
                                 f"TGU: @{user_info[2]}\n" \
                                 f"Телефон: {user_info[4]}\n" \
                                 f"Створено: {rent[11]}\n" \
                                 f"Комірка: {locker[2]} ({_station_label(locker[1])}) | {locker[3]}\n" \
                                 f"Статус: {rent[12]}\n" \
                                 f"Час оренди: {rent[4]}хв\n" \
                                 f"Передоплата: {rent[5]}грн | {rent[6]}\n" \
                                 f"Доплата: {rent[7]}грн | {rent[8]}\n" \
                                 f"{rent_time}\n" \
                                 f"Весь час (доступно при доплаті) {rent[14]}хв"

        dock_array = []
        if rent:
            pay_dock = rent[9]
            pay_id = rent[10]
            dock_array.append((pay_dock, pay_id, '📄 Квитанція'))

        if rent:
            com_dock = rent[15]
            com_id = rent[16]
            dock_array.append((com_dock, com_id, '📄 Комплектація'))

        if per_limit:
            per_dock = per_limit[2]
            per_id = per_limit[3]
            dock_array.append((per_dock, per_id, '📄 Доплата'))

        for dock in dock_array:
            print(dock)

            if dock[0] == 'document':
                await bot.send_document(call.from_user.id, document=dock[1], caption=dock[2])
            elif dock[0] == 'photo':
                await bot.send_photo(call.from_user.id, photo=dock[1], caption=dock[2])
            else:
                print(f"⚠️ Невідомий тип файлу")

        await call.message.answer(about_actual_rent_text, reply_markup=keyboard)
        await clear_messages(call.message.chat.id, call.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")


@router.callback_query(F.data == "f_statistic")
async def f_rent(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)
        all_users = db.get_all_user()
        all_rents = db.get_all_rent()
        actual_rent = db.get_all_actual_rent()
        create_date = datetime.now().strftime("%d.%m.%Y")
        today = db.get_rents_today()
        week = db.get_rents_current_week()
        month = db.get_rents_current_month()

        print(today)

        t_counter = 0
        t_money = 0
        for rent in today:
            if rent[6] == 'OK':
                t_counter += 1
                t_money += int(rent[5])
            if rent[8] == 'ОК':
                t_money += int(rent[7])

        w_counter = 0
        w_money = 0
        for rent in week:
            if rent[6] == 'OK':
                w_counter += 1
                w_money += int(rent[5])
            if rent[8] == 'ОК':
                w_money += int(rent[7])

        m_counter = 0
        m_money = 0
        for rent in month:
            if rent[6] == 'OK':
                m_counter += 1
                m_money += int(rent[5])
            if rent[8] == 'ОК':
                m_money += int(rent[7])

        avg_today = round(t_money / t_counter, 2) if t_counter > 0 else 0
        avg_week = round(w_money / w_counter, 2) if w_counter > 0 else 0
        avg_month = round(m_money / m_counter, 2) if m_counter > 0 else 0

        statistic_text = f'<strong>Статистика</strong>\n\n' \
                         f'Користувачі бота: {len(all_users)}\n' \
                         f'Всього оренд: {len(all_rents)}\n' \
                         f'Активні оренди: {len(actual_rent)}\n' \
                         f'Сьогодні: {t_counter} ор. | {t_money} грн | {avg_today} сер. чек\n' \
                         f'Цей тиждень: {w_counter} ор. | {w_money} грн | {avg_week} сер. чек\n' \
                         f'Цей місяць: {m_counter} ор. | {m_money} грн | {avg_month} сер. чек\n'

        buttons = []
        buttons.append([InlineKeyboardButton(text='Експорт в ехcеl', callback_data=f'export')])
        buttons.append([InlineKeyboardButton(text='🔙 Назад', callback_data=f'back_to_main_menu')])
        keyboard = kb.make_keyboard(buttons)



        await callback.message.answer(statistic_text, reply_markup=keyboard)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)


@router.callback_query(F.data == "export")
async def f_rent(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)
        db.export_all_rent_to_excel("rent_export.xlsx")

        buttons = []
        buttons.append([InlineKeyboardButton(text='🔙 Назад', callback_data=f'f_statistic')])
        keyboard = kb.make_keyboard(buttons)

        file = FSInputFile('rent_export.xlsx')
        await bot.send_document(chat_id=callback.from_user.id, document=file, caption="Експорт таблиці оренд", reply_markup=keyboard)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)