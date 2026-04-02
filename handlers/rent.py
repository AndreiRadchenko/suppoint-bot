from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from config_data.config import Config, load_config
from helper.helper import log_exception, clear_messages
from kb import kb
from datetime import datetime
from create_bot import bot
from db import Database
import base64

config: Config = load_config()
db = Database(config.db.path)
router = Router()


class RentBoard(StatesGroup):
    choosing_station = State()
    choosing_cells = State()
    choosing_rent_time = State()
    waiting_payment = State()
    waiting_payment_proof = State()


async def show_locker_selection(message: Message, state: FSMContext, station_id: int):
    data = await state.get_data()
    selected = data.get("selected_lockers", [])

    free_lockers = db.get_all_available_lockers(station_id)
    if not free_lockers:
        await message.edit_text("Немає доступних комірок на цій станції.", reply_markup=kb.user_menu)
        await state.clear()
        return

    buttons = []
    for locker in free_lockers:
        locker_id = locker[0]
        locker_name = locker[2]
        kit = db.get_inventory_kit_by_locker_and_station_id(station_id, locker_id)
        kit_name = kit[1] if kit else "порожньо"

        selected_marker = "✅ " if locker_id in selected else "◻️ "
        text = f"{selected_marker}{locker_name} — {kit_name}"
        callback_data = f"cell_{locker_id}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=callback_data)])

    buttons.append([InlineKeyboardButton(text="✅ Підтвердити", callback_data="done_cells")])
    buttons.append([InlineKeyboardButton(text="❌ Скасувати", callback_data="rent_cancel")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    locker_text = '🏄‍♂️ <strong>Комплект "Стандарт"</strong> - ідеально для однієї особи з базовим багажем\n\n' \
                  '🌊 Надувна дошка Gladiator Origin 10’6\n' \
                  '🛶 Регульоване весло Profiplast SUP AluS (180–210 см)\n' \
                  '🦺 Рятувальний жилет для безпеки на воді\n' \
                  '📱 Водонепроникний чохол для телефону\n' \
                  '👤 Рекомендований зріст: від 160 см\n' \
                  '⚖️ Максимальна вага користувача: до 110 кг\n\n' \
                  '🌟 <strong>Комплект "Максі"</strong> — більший розмір, краща стійкість при перевезенні  додаткового вантажу\n\n' \
                  '🌊 Надувна дошка Gladiator Origin 10’8\n' \
                  '🛶 Регульоване весло Profiplast SUP AluS (190–220 см)\n' \
                  '🦺 Рятувальний жилет для впевненого катання\n' \
                  '📱 Водонепроникний чохол для телефону \n' \
                  '👤 Рекомендований зріст: від 175 см\n' \
                  '⚖️ Рекомендована вага користувача: понад 85 кг\n\n' \
                  '📍 <strong>Резервація</strong>:\n' \
                  ' <strong>Оберіть одну або кілька комірок:</strong>'

    await message.edit_text(locker_text, reply_markup=keyboard)


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
        "BCD",                 # службова мітка
        "002",                 # версія
        "1",                   # кодування (має бути 2, але кодуємо в UTF-8)
        "UCT",                 # функція
        "",                    # зарезервовано
        payer_name,           # отримувач
        iban,                 # рахунок
        f"UAH{int(amount)}",  # сума
        edrpou,               # код отримувача
        "", "",               # зарезервовано
        purpose,              # призначення
        "", ""                # зарезервовано
    ]

    data = "\n".join(lines)
    base64url = base64.urlsafe_b64encode(data.encode("utf-8")).decode("ascii").rstrip("=")

    return f"https://bank-qr.com.ua/pay/{base64url}"


@router.callback_query(F.data == 'rent_cancel')
async def start_rent(callback: CallbackQuery, state: FSMContext):
    try:
        await bot.answer_callback_query(callback.id)
        await callback.message.answer('Оренду скасовано', reply_markup=kb.user_menu)

        user_reserve = db.get_all_reserve_by_tg(callback.from_user.id)

        if len(user_reserve) > 0:
            for reserve in user_reserve:
                db.cancel_rent('Скасовано користувачем', reserve[0])
                db.locker_status('Доступна оренда', reserve[3])

        await state.clear()

        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)

# --- СТАРТ ОРЕНДИ ---
@router.callback_query(F.data == 'rent')
async def start_rent(callback: CallbackQuery, state: FSMContext):
    try:
        await bot.answer_callback_query(callback.id)

        stations = db.get_all_active_stations()
        if not stations:
            await callback.message.answer("🚫 Наразі немає доступних станцій.", reply_markup=kb.user_menu)
            await state.clear()

        keyboard_buttons = [
            [InlineKeyboardButton(text=f"{station[1]} {station[2]}", callback_data=f"station_{station[0]}")]
            for station in stations
        ]

        keyboard_buttons.append([InlineKeyboardButton(text="❌ Скасувати", callback_data="rent_cancel")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await callback.message.answer("📍 <strong>Резервація</strong>:\n<strong>Оберіть станцію прокату</strong>\n", reply_markup=keyboard)
        await state.set_state(RentBoard.choosing_station)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)


# --- ВИБІР СТАНЦІЇ ---
@router.callback_query(F.data.startswith("station_"))
async def choose_station(callback: CallbackQuery, state: FSMContext):
    try:
        await bot.answer_callback_query(callback.id)
        station_id = int(callback.data.split("_")[1])
        await state.update_data(station_id=station_id, selected_lockers=[])

        await show_locker_selection(callback.message, state, station_id)
    except Exception as e:
        log_exception(e)


# --- ВИБІР КОМІРОК (Мультивибір) ---
@router.callback_query(F.data.startswith("cell_"))
async def toggle_locker_selection(callback: CallbackQuery, state: FSMContext):
    try:
        await bot.answer_callback_query(callback.id)
        locker_id = int(callback.data.split("_")[1])
        data = await state.get_data()
        selected = data.get("selected_lockers", [])

        if locker_id in selected:
            selected.remove(locker_id)
        else:
            selected.append(locker_id)

        await state.update_data(selected_lockers=selected)
        station_id = data.get("station_id")
        await show_locker_selection(callback.message, state, station_id)
    except Exception as e:
        log_exception(e)


# --- Завершення вибору комірок ---
@router.callback_query(F.data == "done_cells")
async def done_selecting_cells(callback: CallbackQuery, state: FSMContext):
    try:
        await bot.answer_callback_query(callback.id)
        data = await state.get_data()
        selected = data.get("selected_lockers", [])

        if not selected:
            await callback.answer("Оберіть хоча б одну комірку!", show_alert=True)
            return

        data = await state.get_data()
        now = datetime.now()
        create_date = now.strftime("%d.%m.%Y %H:%M")
        for locker_id in selected:
            # Створюємо оренду зі статусом і таймером
            # Таймер задається виходячи з інтервала 15сек (1хв = 4, 60хв = 240)
            db.add_base_rent(callback.from_user.id, data.get('station_id'), locker_id, create_date, 'Резервація', 60)
            db.locker_status("Резервація", locker_id)

        await state.set_state(RentBoard.choosing_rent_time)

        btn1 = InlineKeyboardButton(text="15хв", callback_data="time_15")
        btn2 = InlineKeyboardButton(text="30хв", callback_data="time_30")
        btn3 = InlineKeyboardButton(text="45хв", callback_data="time_45")
        btn4 = InlineKeyboardButton(text="60хв", callback_data="time_60")
        btn5 = InlineKeyboardButton(text="Більше", callback_data="time_more")
        btn6 = InlineKeyboardButton(text="❌ Скасувати", callback_data="rent_cancel")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [btn1, btn2],
            [btn3, btn4],
            [btn5],
            [btn6]
        ])

        await callback.message.answer("📍 <strong>Резервація:</strong>\n<strong>Оберіть тривалість оренди</strong>", reply_markup=keyboard)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)


# --- ВИБІР ТРИВАЛОСТІ ОРЕНДИ ---
@router.callback_query(RentBoard.choosing_rent_time, F.data.startswith("time_"))
async def choose_rent_time(callback: CallbackQuery, state: FSMContext):
    try:
        await bot.answer_callback_query(callback.id)
        data = await state.get_data()
        time = callback.data.split("_")[1]
        if time == 'more':
            await state.set_state(RentBoard.choosing_rent_time)
            btn1 = InlineKeyboardButton(text="15хв", callback_data="time_15")
            btn2 = InlineKeyboardButton(text="30хв", callback_data="time_30")
            btn3 = InlineKeyboardButton(text="45хв", callback_data="time_45")
            btn4 = InlineKeyboardButton(text="60хв", callback_data="time_60")
            btn5 = InlineKeyboardButton(text="1год 15хв", callback_data="time_75")
            btn6 = InlineKeyboardButton(text="1год 30хв", callback_data="time_90")
            btn7 = InlineKeyboardButton(text="1год 45хв", callback_data="time_105")
            btn8 = InlineKeyboardButton(text="2год", callback_data="time_120")
            btn9 = InlineKeyboardButton(text="2год 15хв", callback_data="time_135")
            btn10 = InlineKeyboardButton(text="2год 30хв", callback_data="time_150")
            btn11 = InlineKeyboardButton(text="2год 45хв", callback_data="time_165")
            btn12 = InlineKeyboardButton(text="3год", callback_data="time_180")
            btn13 = InlineKeyboardButton(text="3год 15хв", callback_data="time_195")
            btn14 = InlineKeyboardButton(text="3год 30хв", callback_data="time_210")
            btn15 = InlineKeyboardButton(text="3год 45хв", callback_data="time_225")
            btn16 = InlineKeyboardButton(text="4год", callback_data="time_240")
            btn17 = InlineKeyboardButton(text="5год", callback_data="time_300")
            btn18 = InlineKeyboardButton(text="8год", callback_data="time_500")
            btn19 = InlineKeyboardButton(text="❌ Скасувати", callback_data="rent_cancel")
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [btn1, btn2, btn3],
                [btn4, btn5, btn6],
                [btn7, btn8, btn9],
                [btn10, btn11, btn12],
                [btn13, btn14, btn15],
                [btn16, btn17, btn18],
                [btn19]
            ])

            await callback.message.answer("📍 <strong>Резервація:</strong>\n<strong>Оберіть тривалість оренди</strong>",
                                          reply_markup=keyboard)
            await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
        else:
            time = int(callback.data.split("_")[1])
            selected = data.get("selected_lockers", [])
            station_id = data.get("station_id")
            today = datetime.today()
            week_day = today.weekday()
            day_type = 'weekday'

            if week_day >= 5:
                day_type = 'weekend'

            all_price = []
            for locker_id in selected:
                inventory_kit = db.get_inventory_kit_by_locker_and_station_id(station_id, locker_id)
                inventory_kit_name = inventory_kit[1]
                tariff_type = inventory_kit[4]
                price = db.get_tariff_by_data(tariff_type, day_type, time)
                price_per_time = price[4]
                price_for_locker = [inventory_kit_name, price_per_time]
                db.update_price_and_time_in_rent(callback.from_user.id, station_id, locker_id, price_per_time, time)
                all_price.append(price_for_locker)

            price_text = '💳 Оплата:\n' \
                         '🔐 Для підтвердження вашої резервації, будь ласка, здійсніть оплату протягом 🕐 5 хвилин\n' \
                         '📸 Надішліть скріншот або фото квитанції після оплати\n\n' \
                         '📌 До сплати:\n'
            sum_price = 0
            for name, price_val in all_price:
                price_text += f"Комплект <strong>{name} — {price_val} грн</strong>\n"
                sum_price += int(price_val)

            price_text += f'🔢 Всього: <strong>{sum_price} грн</strong>\n\n🕐<strong>Тривалість оренди: {time} хв 👉 Після підтвердження оплати ви отримаєте доступ до спорядження.</strong>'

            await state.update_data(time=time, today=today, week_day=week_day, day_type=day_type, sum_price=sum_price)

            await state.set_state(RentBoard.waiting_payment)

            price_url = generate_bank_qr_url(
                payer_name=config.payment.payer_name,
                iban=config.payment.iban,
                amount=sum_price,
                edrpou=config.payment.edrpou,
                purpose=config.payment.purpose,
            )

            btn1 = InlineKeyboardButton(text="💳 Перейти до оплат", url=price_url)
            btn2 = InlineKeyboardButton(text="❌ Скасувати", callback_data="rent_cancel")
            pay_menu = InlineKeyboardMarkup(inline_keyboard=[
                [btn1],
                [btn2]
            ])

            await callback.message.answer(price_text, reply_markup=pay_menu)

            await state.set_state(RentBoard.waiting_payment_proof)
            await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)


# --- ОТРИМАННЯ СКРІНУ ---
@router.message(RentBoard.waiting_payment_proof, F.photo | F.document)
async def payment_proof_received(message: Message, state: FSMContext):
    try:
        data = await state.get_data()

        file_type = None
        file_id = None

        if message.photo:
            file_type = "photo"
            file_id = message.photo[-1].file_id
        elif message.document:
            file_type = "document"
            file_id = message.document.file_id

        data["payment_file_type"] = file_type
        data["payment_file_id"] = file_id

        await state.update_data(payment_file_type=file_type, payment_file_id=file_id)

        # Підтвердження
        await message.answer("✅ Очікуйте перевірку менеджером (до 5 хвилин)")

        data = await state.get_data()

        for locker_id in data.get('selected_lockers'):
            db.locker_status("Перевірка оплати", locker_id)
            db.update_status_and_timer_for_rent(message.from_user.id, data.get("station_id"), locker_id, 'Перевірка оплати', 0, file_type, file_id, 'Резервація')

        for admin in config.tg_bot.admin_ids:
            await bot.send_message(admin, "✅ Новий запит на аренду. Потрібо перевірити", reply_markup=kb.admin_menu)

        await state.clear()
        await clear_messages(message.chat.id, message.message_id, 15)
    except Exception as e:
        log_exception(e)

# --- НЕСКРІН ФОТО ---
@router.message(RentBoard.waiting_payment_proof)
async def not_photo(message: Message, state: FSMContext):
    try:
        await message.answer("❗ Надішліть саме фото квитанції або скріншот оплати.")
    except Exception as e:
        log_exception(e)
