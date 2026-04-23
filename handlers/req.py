from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config_data.config import Config, load_config
from kb import kb
from create_bot import bot
from db import Database
from helper.helper import log_exception, clear_messages

config: Config = load_config()
db = Database(config.db.path)
router = Router()


class RegisterFSM(StatesGroup):
    name = State()
    phone = State()
    consent = State()
    confirm = State()


CANCEL_TEXT = "❌ Скасувати реєстрацію"

cancel_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=CANCEL_TEXT)]],
    resize_keyboard=True,
    one_time_keyboard=True
)

phone_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📞 Надіслати номер телефону", request_contact=True)],
        [KeyboardButton(text=CANCEL_TEXT)]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)


# 🔄 Загальна перевірка на скасування
async def cancel_check(message: Message, state: FSMContext):
    if message.text == CANCEL_TEXT:
        await send_cancel_message(message)
        await state.clear()
        return True
    return False


async def send_cancel_message(message: Message):
    try:
        await message.answer("Реєстрацію скасовано.", reply_markup=ReplyKeyboardRemove())
        await message.answer("Оберіть дію", reply_markup=kb.reg_menu)
        await clear_messages(message.chat.id, message.message_id, 15)
    except Exception as e:
        log_exception(e)


@router.callback_query(F.data == "req_start")
async def start_register(callback: CallbackQuery, state: FSMContext):
    try:
        await bot.answer_callback_query(callback.id)
        await state.set_state(RegisterFSM.name)
        await callback.message.answer("Введіть ваше ім’я:", reply_markup=cancel_kb)
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)


@router.message(RegisterFSM.name)
async def get_name(message: Message, state: FSMContext):
    try:
        if await cancel_check(message, state):
            return

        await state.update_data(name=message.text)
        await state.set_state(RegisterFSM.phone)
        await message.answer("Поділіться своїм номером телефону:", reply_markup=phone_kb)
        await clear_messages(message.chat.id, message.message_id, 15)
    except Exception as e:
        log_exception(e)


@router.message(RegisterFSM.phone)
async def get_phone(message: Message, state: FSMContext):
    try:
        # Accept both Telegram contact button and plain text input
        phone_value = None
        if message.contact:
            phone_value = message.contact.phone_number
        elif message.text:
            phone_value = message.text.strip()

        if not phone_value:
            await message.answer("Будь ласка, надішліть номер телефону або використайте кнопку.", reply_markup=phone_kb)
            return

        await state.update_data(phone=phone_value)
        await state.set_state(RegisterFSM.consent)

        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Погоджуюсь", callback_data="consent_yes")
        builder.button(text="❌ Не погоджуюсь", callback_data="consent_no")

        await message.answer("⏳ Телефон збережено...", reply_markup=ReplyKeyboardRemove())
        await message.answer(
            "Чи погоджуєтесь ви на обробку персональних даних?",
            reply_markup=builder.as_markup()
        )
        await clear_messages(message.chat.id, message.message_id, 15)
    except Exception as e:
        log_exception(e)


@router.callback_query(RegisterFSM.consent, F.data.in_(["consent_yes", "consent_no"]))
async def handle_consent(callback: CallbackQuery, state: FSMContext):
    try:
        await bot.answer_callback_query(callback.id)

        if callback.data == "consent_no":
            await callback.message.answer("Реєстрацію скасовано.", reply_markup=kb.reg_menu)
            await state.clear()
            return

        await state.set_state(RegisterFSM.confirm)
        data = await state.get_data()

        text = (
            f"🔍 Перевірте введені дані:\n\n"
            f"👤 Ім’я: `{data['name']}`\n"
            f"📞 Телефон: `{data['phone']}`\n\n"
            f"Підтвердити реєстрацію?"
        )

        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Підтвердити", callback_data="register_confirm")
        builder.button(text="❌ Скасувати", callback_data="register_cancel")

        await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
        await clear_messages(callback.message.chat.id, callback.message.message_id, 15)
    except Exception as e:
        log_exception(e)


@router.callback_query(RegisterFSM.confirm, F.data.in_(["register_confirm", "register_cancel"]))
async def confirm_registration(callback: CallbackQuery, state: FSMContext):
    try:
        if callback.data == "register_cancel":
            await callback.message.answer("Реєстрацію скасовано.")
            await state.clear()
            return

        data = await state.get_data()
        create_date = datetime.now(ZoneInfo('Europe/Kyiv')).strftime("%Y-%m-%d %H:%M")

        db.add_new_user(
            tg_id=callback.from_user.id,
            tg_un=callback.from_user.username,
            name=data.get('name'),
            phone=data.get('phone'),
            create_data=create_date,
            role='client'
        )

        await callback.message.answer("🎉 Реєстрація успішна!", reply_markup=ReplyKeyboardRemove())
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
