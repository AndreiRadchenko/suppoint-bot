from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import StateFilter
from config_data.config import Config, load_config
from create_bot import bot
from kb import kb
from helper.helper import clear_messages
from db import Database

config: Config = load_config()
db = Database(config.db.path)
router = Router()

# ======= СТАНИ =======
class ReportProblem(StatesGroup):
    waiting_for_text = State()
    waiting_for_file = State()
    confirm = State()

# ======= КНОПКИ =======
def confirm_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Підтвердити", callback_data="confirm_problem")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel_problem")]
    ])

def skip_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустити", callback_data="skip_file")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel_problem")]
    ])

# ======= СТАРТ =======
@router.callback_query(F.data == "error_report")
async def start_report(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer("📝 Опишіть проблему:")
        await state.set_state(ReportProblem.waiting_for_text)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")

# ======= ПРИЙОМ ТЕКСТУ =======
@router.message(StateFilter(ReportProblem.waiting_for_text), F.text)
async def get_problem_text(message: Message, state: FSMContext):
    try:
        await state.update_data(description=message.text)
        await message.answer("📎 Надішліть фото або документ (або натисніть 'Пропустити')", reply_markup=skip_keyboard())
        await state.set_state(ReportProblem.waiting_for_file)
        await clear_messages(message.chat.id, message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")

# ======= ПРИЙОМ ФАЙЛУ =======
@router.message(StateFilter(ReportProblem.waiting_for_file), F.content_type.in_({'photo', 'document'}))
async def get_problem_file(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        if message.photo:
            file_type = "photo"
            file_id = message.photo[-1].file_id
        elif message.document:
            file_type = "document"
            file_id = message.document.file_id
        await state.update_data(file_id=file_id, file_type=file_type)
        text = f"🔔 Ви описали проблему:\n\n{data['description']}\n\n📎 Додано файл."
        await message.answer(text, reply_markup=confirm_keyboard())
        await state.set_state(ReportProblem.confirm)
        await clear_messages(message.chat.id, message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")

# ======= ПРОПУСТИТИ ФАЙЛ =======
@router.callback_query(StateFilter(ReportProblem.waiting_for_file), F.data == "skip_file")
async def skip_file(call: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        await call.message.edit_text(f"🔔 Ви описали проблему:\n\n{data['description']}\n\n(Без файлу)", reply_markup=confirm_keyboard())
        await state.set_state(ReportProblem.confirm)
        await clear_messages(call.message.chat.id, call.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")

# ======= ПІДТВЕРДЖЕННЯ =======
@router.callback_query(StateFilter(ReportProblem.confirm), F.data == "confirm_problem")
async def confirm_problem(call: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()

        user = db.get_user_by_tg_id(call.from_user.id)
        current_rent = db.get_all_my_rent(call.from_user.id)
        current_rent_text = ''
        if len(current_rent) > 0:
            for rent in current_rent:
                current_rent_text += f'Станція ID: {rent[2]} | Комврка ID: {rent[3]}\n'
        else:
            current_rent_text = 'Аренда відсутня'

        now = datetime.now()
        create_date = now.strftime("%d.%m.%Y %H:%M")

        db.create_problem_report(user[1], user[2], user[4], current_rent_text, data.get('file_type'), data.get('file_id'), data.get('description'), 'Новий', create_date)

        for admin in config.tg_bot.admin_ids:
            await bot.send_message(admin, "✅ Нове повідомлення про проблему", reply_markup=kb.admin_menu)

        await call.message.edit_text("✅ Ваше повідомлення про проблему надіслано. Дякуємо!", reply_markup=kb.user_menu)
        await state.clear()
        await clear_messages(call.message.chat.id, call.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")

# ======= СКАСУВАННЯ =======
@router.callback_query(F.data == "cancel_problem")
async def cancel_problem(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.edit_text("❌ Повідомлення про проблему скасовано.", reply_markup=kb.user_menu)
        await state.clear()
        await clear_messages(call.message.chat.id, call.message.message_id, 15)
    except Exception as e:
        print(f"🚨 Загальна помилка: {e}")
