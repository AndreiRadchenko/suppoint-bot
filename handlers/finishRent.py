import base64
from contextlib import suppress
from datetime import datetime
from math import ceil

from aiogram import Router, F, types
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.utils.media_group import MediaGroupBuilder
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.state import StatesGroup, State
from db import Database
from create_bot import bot
from helper.helper import clear_messages, log_exception, get_entity_state
from kb import kb
from text.text import MSG_USER_WELCOME
from config_data.config import Config, load_config
from services.payments import PaymentService

config: Config = load_config()
db = Database(config.db.path)
payment_service = PaymentService()


def _normalize_ha_url(url: str) -> str:
    normalized = (url or '').strip()
    if normalized.startswith("http://") or normalized.startswith("https://"):
        return normalized
    return f"http://{normalized}"


def _station_ha_for_locker(locker):
    station = db.get_station_by_id(locker[1])
    if not station:
        raise RuntimeError(f"Станцію {locker[1]} не знайдено")

    ha_url = (station[7] or '').strip()
    ha_token = (station[8] or '').strip()
    if not ha_url or not ha_token:
        raise RuntimeError(f"Для станції #{station[0]} не налаштований station-level Home Assistant")

    return _normalize_ha_url(ha_url), ha_token


def _station_label(station_id: int) -> str:
    station = db.get_station_by_id(station_id)
    if not station:
        return f"Станція #{station_id}"

    station_location = (station[2] or "").strip()
    if station_location:
        return station_location
    return f"Станція #{station_id}"


class RentFinishFSM(StatesGroup):
    waiting_for_photo = State()
    waiting_for_confirmation = State()


router = Router()


def generate_bank_qr_url(
        payer_name: str,
        iban: str,
        amount: float,
        edrpou: str,
        purpose: str
) -> str:
    """
    Генерує URL для оплати через https://bank-qr.com.ua/pay/<...>
    Використовує UTF-8, оскільки Windows-1251 не підтримується на сайті.
    """

    lines = [
        "BCD",  # службова мітка
        "002",  # версія
        "1",  # кодування (має бути 2, але кодуємо в UTF-8)
        "UCT",  # функція
        "",  # зарезервовано
        payer_name,  # отримувач
        iban,  # рахунок
        f"UAH{int(amount)}",  # сума
        edrpou,  # код отримувача
        "", "",  # зарезервовано
        purpose,  # призначення
        "", ""  # зарезервовано
    ]

    data = "\n".join(lines)
    base64url = base64.urlsafe_b64encode(data.encode("utf-8")).decode("ascii").rstrip("=")

    return f"https://bank-qr.com.ua/pay/{base64url}"


@router.callback_query(F.data == 'finish_rent_cancel')
async def start_rent(callback: CallbackQuery, state: FSMContext):
    try:
        await bot.answer_callback_query(callback.id)
        await callback.message.answer(MSG_USER_WELCOME, reply_markup=kb.user_menu)

        await state.clear()

        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)


# Старт завершення оренди
@router.callback_query(F.data.startswith("finishRent:"))
async def start_rent_finish(callback: CallbackQuery, state: FSMContext):
    try:
        await bot.answer_callback_query(callback.id)
        rent_id = callback.data.split(":")[-1]
        await state.update_data(rent_id=rent_id)

        rent = db.get_rent_by_id(rent_id)
        locker_id = rent[3]
        current_locker = db.get_locker_by_locker_id(locker_id)
        inventory_kit = db.get_inventory_kit_by_locker_and_station_id(rent[2], locker_id)
        station_label = _station_label(rent[2])

        await state.update_data(locker_id=locker_id)

        fin_text = f'⏳ Кінець оренди: Комірка {current_locker[2]} ({station_label}) {inventory_kit[1]}. \n\n' \
                   '✨ Переконайтесь, що спорядження чисте та неушкоджене перед поверненням.\n' \
                   '📦 Заберіть всі свої речі з комірки.\n' \
                   '❗️ Якщо щось пошкоджено або зіпсовано — надішліть фото та коротке повідомлення в 🛟Підтримку\n\n' \
                   '📍 Поверніть спорядження на місце:\n' \
                   '🏄‍♂️ Сапборд \n' \
                   '🚣‍♀️ Весло\n' \
                   '🦺 Рятувальний жилет\n' \
                   '📱 Водонепроникний чохол для телефону\n\n' \
                   f'📸 <strong>Надішліть фото комплекту {inventory_kit[1]} в Комірка {current_locker[2]} ({station_label})</strong>'
        photo_kit = FSInputFile("media/kit.jpg")

        await bot.send_photo(callback.from_user.id, photo=photo_kit, caption=fin_text, reply_markup=kb.finish_rent_cancel_menu)
        await state.set_state(RentFinishFSM.waiting_for_photo)
        await callback.answer()
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)


# Отримання фото
@router.message(RentFinishFSM.waiting_for_photo, F.photo | F.document)
async def photo_received(message: Message, state: FSMContext):
    try:
        file_type = None
        file_id = None
        data = await state.get_data()
        rent_id = data.get("rent_id")

        if message.photo:
            file_type = "photo"
            file_id = message.photo[-1].file_id
        elif message.document:
            file_type = "document"
            file_id = message.document.file_id

        db.rent_update_complect_photo(file_type, file_id, rent_id)
        rent = db.get_rent_by_id(rent_id) if rent_id else None
        station_location = _station_label(rent[2]) if rent else "Невідома локація"
        locker_number = "?"
        start_time = "Невідомо"

        if rent:
            start_time = rent[11] or "Невідомо"
            locker = db.get_locker_by_locker_id(rent[3])
            if locker:
                locker_number = locker[2]

        admin_caption = (
            f"Комплектація до звершення Ореннди {rent_id}\n"
            f"Локація: {station_location}\n"
            f"Комірка: {locker_number}\n"
            f"Початок оренди: {start_time}"
        )

        for admin in config.tg_bot.admin_ids:
            if file_type == "document":
                await bot.send_document(admin, file_id, caption=admin_caption,
                                        reply_markup=kb.admin_menu)
            else:
                await bot.send_photo(admin, file_id, caption=admin_caption,
                                     reply_markup=kb.admin_menu)

        await state.update_data(file_type=file_type, file_id=file_id)

        confirm_btn = kb.rent_finish_confirm_menu
        await message.answer(
            "✅ Фото збережено!\n\nТепер закрийте дверцята комірки та натисніть кнопку нижче:",
            reply_markup=confirm_btn
        )
        await state.set_state(RentFinishFSM.waiting_for_confirmation)
        await clear_messages(message.chat.id, message.message_id, 15)
    except Exception as e:
        log_exception(e)

# Завершення оренди
@router.callback_query(RentFinishFSM.waiting_for_confirmation, F.data == "confirm_rent_finish")
async def finish_rent(callback: CallbackQuery, state: FSMContext):
    try:
        with suppress(TelegramBadRequest):
            await callback.answer("Перевіряю стан комірки...")

        info = await state.get_data()
        locker_id = info.get('locker_id')
        current_locker = db.get_locker_by_locker_id(locker_id)
        if not current_locker:
            await callback.message.answer("⚠️ Не вдалося знайти комірку. Спробуйте завершити оренду ще раз.")
            return

        sensor = current_locker[5]
        print('sensor', sensor)
        try:
            ha_url, ha_token = _station_ha_for_locker(current_locker)
        except RuntimeError as exc:
            await callback.message.answer(f"⚠️ {exc}")
            return

        sensor_status = await get_entity_state(sensor, ha_url, ha_token)
        print('sensor_status', sensor_status)
        if sensor_status is None:
            confirm_btn = kb.rent_finish_confirm_menu
            await callback.message.answer(
                "⚠️ Не вдалося зв'язатися зі станцією, вона зараз недоступна. "
                "Спробуйте ще раз за хвилину або скасуйте завершення оренди.",
                reply_markup=confirm_btn
            )
            await state.set_state(RentFinishFSM.waiting_for_confirmation)
            return

        if sensor_status == 'close' or sensor_status == 'closed' or sensor_status == 'off' or sensor_status == 'False' or sensor_status == 'false':
            data = await state.get_data()
            rent_id = data.get("rent_id")
            rent = db.get_rent_by_id(rent_id)

            if int(rent[13]) > -20:
                db.rent_update_status_and_timer('Завершено', 0, rent[0])
                db.add_total_time(rent[4], rent[0])
                rent_counter = db.get_all_my_rent(rent[1])
                if len(rent_counter) > 0:
                    await callback.message.answer(f"✅ Оренду №{rent_id} завершено. Дякуємо!\n\nУ вас залишилися оренди, які ще не завершено.", reply_markup=kb.user_menu)
                else:

                    await callback.message.answer(f"✅ Оренду №{rent_id} завершено. Дякуємо!")
                await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
                await state.clear()
            else:
                base_time = rent[4]
                base_pay = rent[5]
                perlimit = rent[13]

                total = int(base_time) + (int(perlimit) * -1 / 4)

                total_time = ceil(total / 15) * 15

                if total_time > 300:
                    total_time = 480
                elif total_time > 240:
                    total_time = 300

                today = datetime.today()
                week_day = today.weekday()
                day_type = 'weekday'

                if week_day >= 5:
                    day_type = 'weekend'

                locker_id = rent[3]
                inventory_kit = db.get_inventory_kit_by_locker_and_station_id(rent[2], locker_id)
                tariff_type = inventory_kit[4]
                price = db.get_tariff_by_data(tariff_type, day_type, total_time)
                price_per_time = price[4]

                fin_pay = int(price_per_time) - int(base_pay)

                if fin_pay <= 0:
                    db.rent_update_status_and_timer('Завершено', 0, rent[0])
                    db.add_total_time(rent[4], rent[0])
                    rent_counter = db.get_all_my_rent(rent[1])
                    if len(rent_counter) > 0:
                        await callback.message.answer(
                            f"✅ Оренду №{rent_id} завершено. Дякуємо!\n\nУ вас залишилися оренди, які ще не завершено.",
                            reply_markup=kb.user_menu)
                    else:
                        await callback.message.answer(f"✅ Оренду №{rent_id} завершено. Дякуємо!")
                    await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
                    await state.clear()
                else:
                    station = db.get_station_by_id(rent[2])
                    station_name = (station[1] if station and station[1] else f"#{rent[2]}").strip()
                    station_location = (station[2] if station and station[2] else "").strip()
                    if station_location:
                        topup_destination = f"Доплата за оренду #{rent_id}. Станція: {station_name} ({station_location})"
                    else:
                        topup_destination = f"Доплата за оренду #{rent_id}. Станція: {station_name}"

                    price_url, topup_invoice_id = await payment_service.create_topup_invoice(
                        rent_id=rent_id,
                        tg_id=rent[1],
                        amount_grn=fin_pay,
                        destination=topup_destination,
                    )

                    db.rent_update_surcharge(fin_pay, rent_id)

                    pay_menu = kb.topup_pay_menu(price_url)

                    sent = await callback.message.answer('💰Доплата:\n'
                                                  f'Мабуть, ваша прогулянка була надто крута 😎 Трохи перевищили оренду, тож просимо доплатити {fin_pay} грн 🪙\n'
                                                  f'⏱️ Загальна тривалість оренди склала {total_time} хв.\n'
                                                  '⚡️ Після оплати підтвердження відбудеться автоматично.\n'
                                                  '🙌 Дякуємо, що обираєте нас та чекаємо знову!'
                                                  , reply_markup=pay_menu)
                    db.save_link_message_id(topup_invoice_id, sent.message_id)

                    db.rent_update_status_and_timer('Очікує доплату', 0, rent[0])
                    db.add_total_time(total_time, rent[0])
                    await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
                    await state.clear()
            db.locker_status("Доступна оренда", rent[3])
        else:
            print('Ой не закрито')
            station_label = _station_label(current_locker[1])
            confirm_btn = kb.rent_finish_confirm_menu
            await callback.message.answer(
                f"Комірка {current_locker[2]} ({station_label}) не закрита. Закрийте та натисніть 🔒 Кінець оренди ще аз:",
                reply_markup=confirm_btn
            )
            await state.set_state(RentFinishFSM.waiting_for_confirmation)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)
        with suppress(TelegramBadRequest):
            await callback.message.answer(
                "⚠️ Не вдалося завершити оренду через технічну помилку. Спробуйте ще раз пізніше."
            )

