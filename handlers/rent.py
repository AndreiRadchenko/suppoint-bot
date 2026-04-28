from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from config_data.config import Config, load_config
from helper.helper import log_exception, clear_messages
from kb import kb
from datetime import datetime
from zoneinfo import ZoneInfo
from create_bot import bot
from db import Database
import base64
from services.payments import PaymentService

config: Config = load_config()
db = Database(config.db.path)
payment_service = PaymentService()
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
    station = db.get_station_by_id(station_id)
    station_location = (station[2] if station and station[2] else "").strip()
    station_label = station_location if station_location else f"Станція #{station_id}"

    free_lockers = db.get_all_available_lockers(station_id)
    if not free_lockers:
        await message.edit_text("Немає доступних комірок на цій станції.", reply_markup=kb.user_menu)
        await state.clear()
        return

    configured_lockers = []
    skipped_count = 0
    for locker in free_lockers:
        locker_id = locker[0]
        kit = db.get_inventory_kit_by_locker_and_station_id(station_id, locker_id)
        if not kit:
            skipped_count += 1
            continue
        configured_lockers.append((locker, kit))

    if not configured_lockers:
        await message.edit_text(
            "Немає доступних комірок із налаштованим комплектом на цій станції.",
            reply_markup=kb.user_menu,
        )
        await state.clear()
        return

    configured_ids = {locker[0] for locker, _ in configured_lockers}
    selected = [locker_id for locker_id in selected if locker_id in configured_ids]
    await state.update_data(selected_lockers=selected)

    buttons = []
    for locker, kit in configured_lockers:
        locker_id = locker[0]
        locker_name = locker[2]
        kit_name = kit[1]

        selected_marker = "✅ " if locker_id in selected else "◻️ "
        text = f"{selected_marker}{locker_name} ({station_label}) — {kit_name}"
        callback_data = f"cell_{locker_id}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=callback_data)])

    keyboard = kb.rent_locker_keyboard(buttons)

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

    if skipped_count:
        locker_text += (
            f"\n\n⚠️ {skipped_count} комірок приховано, "
            "бо для них не налаштовано комплект/тариф."
        )

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

        # --- ПЕРЕВІРКА НЕСПЛАЧЕНИХ ДОПЛАТ ---
        unpaid = db.get_unpaid_surcharges_by_user(callback.from_user.id)
        if unpaid:
            lines = []
            for sc in unpaid:
                tx = db.get_topup_tx_by_surcharge_id(sc[0])
                if tx and tx[11]:
                    lines.append(f"• Оренда #{sc[6]}: <a href='{tx[11]}'>Оплатити доплату</a>")
                else:
                    lines.append(f"• Оренда #{sc[6]}: очікує обробки адміністратором")
            links_text = "\n".join(lines)
            await callback.message.answer(
                f"🚫 <b>Нова оренда заблокована</b>\n\n"
                f"У вас є несплачені доплати за попередні оренди. "
                f"Будь ласка, сплатіть борг, щоб розпочати нову оренду.\n\n"
                f"{links_text}",
                reply_markup=kb.user_menu,
                parse_mode='HTML',
            )
            await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
            await state.clear()
            return

        stations = db.get_visible_stations()
        if not stations:
            await callback.message.answer("🚫 Наразі немає доступних станцій.", reply_markup=kb.user_menu)
            await state.clear()
            return

        keyboard_buttons = []
        for station in stations:
            station_id = station[0]
            location_label = station[2] or f"Станція #{station_id}"
            is_active = bool(station[4])
            if is_active:
                text = f"🟢 {location_label}"
                callback_data = f"station_{station_id}"
            else:
                text = f"🔴 {location_label} (неактивна)"
                callback_data = f"station_inactive_{station_id}"
            keyboard_buttons.append([InlineKeyboardButton(text=text, callback_data=callback_data)])

        keyboard = kb.rent_station_keyboard(keyboard_buttons)

        await callback.message.answer("📍 <strong>Резервація</strong>:\n<strong>Оберіть станцію прокату</strong>\n", reply_markup=keyboard)
        await state.set_state(RentBoard.choosing_station)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)


@router.callback_query(F.data.regexp(r"^station_inactive_\d+$"))
async def choose_inactive_station(callback: CallbackQuery):
    try:
        await bot.answer_callback_query(callback.id)
        await callback.answer("⚠️ Станція тимчасово неактивна. Оберіть іншу станцію.", show_alert=True)
    except Exception as e:
        log_exception(e)


# --- ВИБІР СТАНЦІЇ ---
@router.callback_query(F.data.regexp(r"^station_\d+$"))
async def choose_station(callback: CallbackQuery, state: FSMContext):
    try:
        await bot.answer_callback_query(callback.id)
        station_id = int(callback.data.split("_")[1])
        station = db.get_station_by_id(station_id)
        if not station:
            await callback.message.answer("❌ Станцію не знайдено.", reply_markup=kb.user_menu)
            await state.clear()
            return

        is_active = bool(station[4])
        is_visible = bool(station[5])
        is_working = station[3] == "work"
        if not (is_active and is_visible and is_working):
            await callback.message.answer(
                "⚠️ Ця станція тимчасово недоступна. Оберіть іншу станцію.",
                reply_markup=kb.user_menu,
            )
            await state.clear()
            return

        await state.update_data(station_id=station_id, selected_lockers=[])

        await show_locker_selection(callback.message, state, station_id)
        # await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)


# --- ВИБІР КОМІРОК (Мультивибір) ---
@router.callback_query(F.data.startswith("cell_"))
async def toggle_locker_selection(callback: CallbackQuery, state: FSMContext):
    try:
        await bot.answer_callback_query(callback.id)
        locker_id = int(callback.data.split("_")[1])
        data = await state.get_data()
        station_id = data.get("station_id")
        if not station_id:
            await callback.answer("Сесію втрачено. Почніть оренду заново.", show_alert=True)
            await state.clear()
            return

        kit = db.get_inventory_kit_by_locker_and_station_id(station_id, locker_id)
        if not kit:
            await callback.answer("Для цієї комірки не налаштовано комплект.", show_alert=True)
            await show_locker_selection(callback.message, state, station_id)
            return

        selected = data.get("selected_lockers", [])

        if locker_id in selected:
            selected.remove(locker_id)
        else:
            selected.append(locker_id)

        await state.update_data(selected_lockers=selected)
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

        # Clear selected_lockers immediately to prevent double-tap creating duplicate rents.
        # Save confirmed list separately so choose_rent_time can still access it.
        await state.update_data(selected_lockers=[], confirmed_lockers=selected)

        data = await state.get_data()
        station_id = data.get('station_id')
        for locker_id in selected:
            if not db.get_inventory_kit_by_locker_and_station_id(station_id, locker_id):
                await callback.answer("Деякі комірки не налаштовані. Оберіть інші.", show_alert=True)
                await show_locker_selection(callback.message, state, station_id)
                return

        # Cancel any stale pending rents for the selected lockers (abandoned bookings).
        # Without this, a second booking for the same locker leaves the first rent in
        # 'Очікує оплату' status and the payment webhook promotes both to 'Очікування відкриття',
        # causing duplicate entries in the user's active-rent menu.
        stale_pending = db.get_all_reserve_by_tg(callback.from_user.id)
        for stale in stale_pending:
            if stale[3] in selected:
                db.cancel_rent('Скасовано користувачем', stale[0])
                db.locker_status('Доступна оренда', stale[3])

        now = datetime.now(ZoneInfo('Europe/Kyiv'))
        create_date = now.strftime("%Y-%m-%d %H:%M")
        for locker_id in selected:
            # Створюємо оренду зі статусом і таймером
            # Таймер задається виходячи з інтервала 15сек (1хв = 4, 60хв = 240)
            db.add_base_rent(callback.from_user.id, station_id, locker_id, create_date, 'Резервація', 60)
            db.locker_status("Резервація", locker_id)

        await state.set_state(RentBoard.choosing_rent_time)

        await callback.message.answer("📍 <strong>Резервація:</strong>\n<strong>Оберіть тривалість оренди</strong>", reply_markup=kb.rent_time_basic_menu)
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
            await callback.message.answer("📍 <strong>Резервація:</strong>\n<strong>Оберіть тривалість оренди</strong>",
                                          reply_markup=kb.rent_time_extended_menu)
            await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
        else:
            time = int(callback.data.split("_")[1])
            selected = data.get("confirmed_lockers") or data.get("selected_lockers", [])
            station_id = data.get("station_id")

            if not selected:
                await callback.answer("Оберіть хоча б одну комірку.", show_alert=True)
                await state.set_state(RentBoard.choosing_cells)
                await show_locker_selection(callback.message, state, station_id)
                return

            today = datetime.today()
            week_day = today.weekday()
            day_type = 'weekday'

            if week_day >= 5:
                day_type = 'weekend'

            all_price = []
            station = db.get_station_by_id(station_id)
            station_name = (station[1] if station and station[1] else f"#{station_id}").strip()
            station_location = (station[2] if station and station[2] else "").strip()
            station_label = station_location if station_location else f"Станція #{station_id}"
            for locker_id in selected:
                inventory_kit = db.get_inventory_kit_by_locker_and_station_id(station_id, locker_id)
                if not inventory_kit:
                    await callback.message.answer(
                        f"⚠️ Комірка ID {locker_id} ({station_label}) не має налаштованого комплекту. Оберіть іншу.",
                        reply_markup=kb.user_menu,
                    )
                    await state.clear()
                    return
                inventory_kit_name = inventory_kit[1]
                tariff_type = inventory_kit[4]
                price = db.get_tariff_by_data(tariff_type, day_type, time)
                if not price:
                    await callback.message.answer(
                        f"⚠️ Для комплекту {inventory_kit_name} немає тарифу на {time} хв ({day_type}).",
                        reply_markup=kb.user_menu,
                    )
                    await state.clear()
                    return
                price_per_time = price[4]
                price_for_locker = [inventory_kit_name, price_per_time]
                db.update_price_and_time_in_rent(callback.from_user.id, station_id, locker_id, price_per_time, time)
                all_price.append(price_for_locker)

            price_text = '💳 Оплата:\n' \
                         '🔐 Для підтвердження вашої резервації, будь ласка, здійсніть оплату протягом 🕐 5 хвилин\n' \
                         '⚡️ Після оплати підтвердження відбудеться автоматично\n\n' \
                         '📌 До сплати:\n'
            sum_price = 0
            for name, price_val in all_price:
                price_text += f"Комплект <strong>{name} — {price_val} грн</strong>\n"
                sum_price += int(price_val)

            price_text += f'🔢 Всього: <strong>{sum_price} грн</strong>\n\n🕐<strong>Тривалість оренди: {time} хв 👉 Після підтвердження оплати ви отримаєте доступ до спорядження.</strong>'

            await state.update_data(time=time, today=today, week_day=week_day, day_type=day_type, sum_price=sum_price)

            await state.set_state(RentBoard.waiting_payment)

            for locker_id in selected:
                db.locker_status("Очікує оплату", locker_id)
                db.update_status_and_timer_for_rent_simple(
                    callback.from_user.id,
                    station_id,
                    locker_id,
                    'Очікує оплату',
                    20,
                    'Резервація',
                )

            if station_location:
                destination = f"Оренда спорядження. Станція: {station_name} ({station_location}). Тривалість {time} хв"
            else:
                destination = f"Оренда спорядження. Станція: {station_name}. Тривалість {time} хв"
            price_url, invoice_id = await payment_service.create_initial_invoice(
                tg_id=callback.from_user.id,
                station_id=station_id,
                locker_ids=selected,
                amount_grn=sum_price,
                destination=destination,
            )

            pay_menu = kb.rent_pay_menu(price_url)

            sent = await callback.message.answer(price_text, reply_markup=pay_menu)
            db.save_link_message_id(invoice_id, sent.message_id)
            await state.clear()
            await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)


# --- ОТРИМАННЯ СКРІНУ ---
@router.message(RentBoard.waiting_payment_proof, F.photo | F.document)
async def payment_proof_received(message: Message, state: FSMContext):
    try:
        await message.answer("Оплата для нових оренд підтверджується автоматично. Фото квитанції надсилати не потрібно ✅")
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
