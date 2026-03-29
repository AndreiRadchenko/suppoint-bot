import base64
from datetime import datetime

from aiogram import Router, F, types
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.utils.media_group import MediaGroupBuilder
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.state import StatesGroup, State
from db import Database
from create_bot import bot
from helper.helper import clear_messages, log_exception, get_entity_state
from kb import kb
from config_data.config import Config, load_config

db = Database('ha_bot.db')
config: Config = load_config()


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
        await callback.message.answer('Як орендувати сапборд?\n\n'
                                      '📍 Резервація — оберіть станцію, комірку та тривалість.\n\n'
                                      '💳 Оплата — оплатіть за посиланням, надішліть фото квитанції.\n\n'
                                      '🚪 Початок оренди — після оплати відкрийте комірку (або автостарт оренди через 5 хв).\n\n'
                                      '⏳ Кінець оренди — поверніть спорядження в комірку, сфотографуйте, надішліть фото й закрийте комірку.\n\n'
                                      '💰 Доплати — у разі перевищення часу чи пошкодження спорядження нараховується додаткова оплата.\n\n'
                                      '✅ Завершення — після перевірки фото бот підтвердить: Оренду завершено',
                                      reply_markup=kb.user_menu)

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

        btn1 = InlineKeyboardButton(text="❌ Скасувати", callback_data="finish_rent_cancel")
        back_menu = InlineKeyboardMarkup(inline_keyboard=[
            [btn1],
        ])

        rent = db.get_rent_by_id(rent_id)
        locker_id = rent[3]
        current_locker = db.get_locker_by_locker_id(locker_id)
        inventory_kit = db.get_inventory_kit_by_locker_and_station_id(rent[2], locker_id)

        await state.update_data(locker_id=locker_id)

        fin_text = f'⏳ Кінець оренди: Комірка {current_locker[2]} {inventory_kit[1]}. \n\n' \
                   '✨ Переконайтесь, що спорядження чисте та неушкоджене перед поверненням.\n' \
                   '📦 Заберіть всі свої речі з комірки.\n' \
                   '❗️ Якщо щось пошкоджено або зіпсовано — надішліть фото та коротке повідомлення в 🛟Підтримку\n\n' \
                   '📍 Поверніть спорядження на місце:\n' \
                   '🏄‍♂️ Сапборд \n' \
                   '🚣‍♀️ Весло\n' \
                   '🦺 Рятувальний жилет\n' \
                   '📱 Водонепроникний чохол для телефону\n\n' \
                   f'📸 <strong>Надішліть фото комплекту {inventory_kit[1]} в Комірка {current_locker[2]}</strong>'
        photo_kit = FSInputFile("media/kit.jpg")

        await bot.send_photo(callback.from_user.id, photo=photo_kit, caption=fin_text, reply_markup=back_menu)
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
        for admin in config.tg_bot.admin_ids:
            if file_type == "document":
                await bot.send_document(admin, file_id, caption=f'Комплектація до звершення Ореннди {rent_id}',
                                        reply_markup=kb.admin_menu,
                                        parse_mode="Markdown")
            else:
                await bot.send_photo(admin, file_id, caption=f'Комплектація до звершення Ореннди {rent_id}',
                                     reply_markup=kb.admin_menu,
                                     parse_mode="Markdown")

        await state.update_data(file_type=file_type, file_id=file_id)

        confirm_btn = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔒 Кінець оренди", callback_data="confirm_rent_finish")],
                [InlineKeyboardButton(text="❌ Скасувати", callback_data="finish_rent_cancel")],
            ]
        )
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
        info = await state.get_data()
        locker_id = info.get('locker_id')
        current_locker = db.get_locker_by_locker_id(locker_id)
        sensor = current_locker[5]
        sensor_status = await get_entity_state(sensor, "http://77.52.246.0:8123","eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiIwMGJjNTAwZjViNDk0YzZmOTFjMTYxZTljZTNmMTVjNCIsImlhdCI6MTc1MjI0MzE0NywiZXhwIjoyMDY3NjAzMTQ3fQ.PSxXmoQuJ3f-VK_dLovInSWKNK8hvh0vR8HugLoR8UM")
        if sensor_status == 'close':
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
                await callback.answer()
            else:
                base_time = rent[4]
                base_pay = rent[5]
                perlimit = rent[13]

                total = int(base_time) + (int(perlimit) * -1 / 4)

                total_time = round(total / 15) * 15

                if total_time > 240:
                    total_time = 300
                elif total_time > 300:
                    total_time = 500

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
                    await callback.answer()
                else:
                    price_url = generate_bank_qr_url(
                        payer_name="ФОП Солдатенко Олексій Володимирович",
                        iban="UA863220010000026004330123067",
                        amount=fin_pay,
                        edrpou="2471811770",
                        purpose="За послуги прокату спортивних товарів"
                    )

                    db.rent_update_surcharge(fin_pay, rent_id)

                    btn1 = InlineKeyboardButton(text="💳 Перейти до оплат", url=price_url)
                    pay_menu = InlineKeyboardMarkup(inline_keyboard=[
                        [btn1],
                    ])

                    await callback.message.answer('💰Доплата:\n'
                                                  f'Мабуть, ваша прогулянка була надто крута 😎 Трохи перевищили оренду, тож просимо доплатити {fin_pay} грн 🪙\n'
                                                  f'⏱️ Загальна тривалість оренди склала {total_time} хв.\n'
                                                  '📸 Надішліть, будь ласка, фото у бот для підтвердження.\n'
                                                  '🙌 Дякуємо, що обираєте нас та чекаємо знову!'
                                                  , reply_markup=pay_menu)

                    db.rent_update_status_and_timer('Очікує доплату', 0, rent[0])
                    db.add_total_time(total_time, rent[0])
                    await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
                    await state.clear()
                    await callback.answer()
            db.locker_status("Доступна оренда", rent[3])
        else:
            print('Ой не закрито')
            confirm_btn = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔒 Кінець оренди", callback_data="confirm_rent_finish")],
                    [InlineKeyboardButton(text="❌ Скасувати", callback_data="finish_rent_cancel")],
                ]
            )
            await callback.message.answer(
                f"Комірка {current_locker[2]} не закрита. Закрийте та натисніть 🔒 Кінець оренди ще аз:",
                reply_markup=confirm_btn
            )
            await state.set_state(RentFinishFSM.waiting_for_confirmation)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)

