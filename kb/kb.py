from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


btn1 = InlineKeyboardButton(text="🏄‍♂️ Орендувати", callback_data="rent")
btn2 = InlineKeyboardButton(text="🛶 Мої оренди", callback_data="my_rent")
btn3 = InlineKeyboardButton(text="🗂️Історія оренд", callback_data="history_rent")
btn4 = InlineKeyboardButton(text="ℹ️ Інформація", callback_data="about_rent_reg")
btn5 = InlineKeyboardButton(text="🛟Підтримка", callback_data="error_report")
user_menu = InlineKeyboardMarkup(inline_keyboard=[
    [btn1],
    [btn2],
    [btn3],
    [btn4],
    [btn5],
])


btn1 = InlineKeyboardButton(text="Перегляд оплат", callback_data="check_pay")
btn2 = InlineKeyboardButton(text="Перегляд скарг", callback_data="check_problem")
btn3 = InlineKeyboardButton(text="Перегляд доплат", callback_data="check_surcharge")
btn4 = InlineKeyboardButton(text="Перегляд документів", callback_data="photo_by_rent")
btn5 = InlineKeyboardButton(text="Статус комірок", callback_data="locker_status")
btn6 = InlineKeyboardButton(text="Оренди", callback_data="rent_by_day")
btn7 = InlineKeyboardButton(text="📦 Комірки", callback_data="f_locker_status")
btn8 = InlineKeyboardButton(text="🛶 Оренди", callback_data="f_rent")
btn9 = InlineKeyboardButton(text="📊 Статистика", callback_data="f_statistic")
btn10 = InlineKeyboardButton(text="🏢 Станції", callback_data="station_management")
admin_menu = InlineKeyboardMarkup(inline_keyboard=[
    [btn10],
    [btn7],
    [btn8],
    [btn9],
    [btn1],
    [btn2],
    [btn3],
    [btn4],
    [btn5],
    [btn6],
])


btn1 = InlineKeyboardButton(text="✍️ Реєстрація", callback_data="req_start")
btn2 = InlineKeyboardButton(text="ℹ️ Про аренду", callback_data="about_rent_not_reg")
reg_menu = InlineKeyboardMarkup(inline_keyboard=[
    [btn1],
    [btn2]
])


btn1 = InlineKeyboardButton(text="ℹ️ Загальна інформація", callback_data="pre_reg_info")
btn2 = InlineKeyboardButton(text="ℹ️ Вартість послуг", callback_data="pre_reg_price")
btn3 = InlineKeyboardButton(text="◀️Назад", callback_data="back_to_main_menu")
pre_reg_info_menu = InlineKeyboardMarkup(inline_keyboard=[
    [btn1],
    [btn2],
    [btn3],
])


btn1 = InlineKeyboardButton(text="Активні", callback_data="active_rents")
btn2 = InlineKeyboardButton(text="Історія", callback_data="history_rents")
btn3 = InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main_menu")
f_rent_menu = InlineKeyboardMarkup(inline_keyboard=[
    [btn1, btn2],
    [btn3],
])


# --- Rent flow ---

rent_time_basic_menu = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="15хв", callback_data="time_15"),
        InlineKeyboardButton(text="30хв", callback_data="time_30"),
    ],
    [
        InlineKeyboardButton(text="45хв", callback_data="time_45"),
        InlineKeyboardButton(text="60хв", callback_data="time_60"),
    ],
    [InlineKeyboardButton(text="Більше", callback_data="time_more")],
    [InlineKeyboardButton(text="❌ Скасувати", callback_data="rent_cancel")],
])

rent_time_extended_menu = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="15хв",     callback_data="time_15"),
        InlineKeyboardButton(text="30хв",     callback_data="time_30"),
        InlineKeyboardButton(text="45хв",     callback_data="time_45"),
    ],
    [
        InlineKeyboardButton(text="60хв",     callback_data="time_60"),
        InlineKeyboardButton(text="1год 15хв", callback_data="time_75"),
        InlineKeyboardButton(text="1год 30хв", callback_data="time_90"),
    ],
    [
        InlineKeyboardButton(text="1год 45хв", callback_data="time_105"),
        InlineKeyboardButton(text="2год",      callback_data="time_120"),
        InlineKeyboardButton(text="2год 15хв", callback_data="time_135"),
    ],
    [
        InlineKeyboardButton(text="2год 30хв", callback_data="time_150"),
        InlineKeyboardButton(text="2год 45хв", callback_data="time_165"),
        InlineKeyboardButton(text="3год",      callback_data="time_180"),
    ],
    [
        InlineKeyboardButton(text="3год 15хв", callback_data="time_195"),
        InlineKeyboardButton(text="3год 30хв", callback_data="time_210"),
        InlineKeyboardButton(text="3год 45хв", callback_data="time_225"),
    ],
    [
        InlineKeyboardButton(text="4год", callback_data="time_240"),
        InlineKeyboardButton(text="5год", callback_data="time_300"),
        InlineKeyboardButton(text="8год", callback_data="time_500"),
    ],
    [InlineKeyboardButton(text="❌ Скасувати", callback_data="rent_cancel")],
])


def rent_station_keyboard(station_rows: list) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        *station_rows,
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="rent_cancel")],
    ])


def rent_locker_keyboard(locker_rows: list) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        *locker_rows,
        [InlineKeyboardButton(text="✅ Підтвердити", callback_data="done_cells")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="rent_cancel")],
    ])


def rent_pay_menu(price_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Перейти до оплат", url=price_url)],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="rent_cancel")],
    ])


# --- Utility ---

def make_keyboard(rows: list) -> InlineKeyboardMarkup:
    """Wrap a pre-built list of button rows in an InlineKeyboardMarkup."""
    return InlineKeyboardMarkup(inline_keyboard=rows)


def my_rent_keyboard(items: list) -> InlineKeyboardMarkup:
    """Build the 'My rents' inline keyboard.

    items: list of (rent_id, locker_name, station_label)
    """
    buttons = []
    for rent_id, locker_name, station_label in items:
        buttons.append([InlineKeyboardButton(
            text=f"🔓 Відкрити комірку {locker_name} ({station_label})",
            callback_data=f"openLocker:{rent_id}"
        )])
    for rent_id, locker_name, station_label in items:
        buttons.append([InlineKeyboardButton(
            text=f"✅ Завершити оренду комірки {locker_name} ({station_label})",
            callback_data=f"finishRent:{rent_id}"
        )])
    buttons.append([InlineKeyboardButton(text="🔄 Оновити", callback_data="refresh_my_rent")])
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="back_to_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)



def problem_fix_keyboard(problem_id) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Вирішено", callback_data=f"fixit:{problem_id}")],
        [InlineKeyboardButton(text="🌀 В процесі", callback_data="solution_in_process")],
    ])


def surcharge_review_keyboard(rents_with_pay2: list, surcharge_id) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"✅ Доплата - {pay2}грн", callback_data=f"perlim:{rent_id}:{surcharge_id}")]
        for rent_id, pay2 in rents_with_pay2
    ]
    rows.append([InlineKeyboardButton(text="🌀 Це спам(", callback_data=f"is_spam:{surcharge_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def station_manage_keyboard(station_id: int, is_active: bool, is_visible: bool) -> InlineKeyboardMarkup:
    next_visibility = 0 if is_visible else 1
    next_active = 0 if is_active else 1
    vis_label = "🙈 Приховати для клієнтів" if is_visible else "👁 Показати для клієнтів"
    active_label = "⏸ Деактивувати" if is_active else "✅ Активувати"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=vis_label, callback_data=f"station_toggle_vis:{station_id}:{next_visibility}")],
        [InlineKeyboardButton(text=active_label, callback_data=f"station_toggle_active:{station_id}:{next_active}")],
        [InlineKeyboardButton(text="🔙 До станцій", callback_data="station_management")],
    ])


def open_locker_retry_keyboard(rent_id) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Спробувати ще раз", callback_data=f"openLocker:{rent_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main_menu")],
    ])


def locker_action_keyboard(locker_id, locker_name: str, station_label: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔓 Відкрити ком.{locker_name} ({station_label})", callback_data=f"adm_openLocker:{locker_id}")],
        [InlineKeyboardButton(text=f"♻️ Резервація  ком.{locker_name} ({station_label})", callback_data=f"adm_reserve:{locker_id}")],
        [InlineKeyboardButton(text="➖ Завершити повязані оренди", callback_data=f"adm_close_rent:{locker_id}")],
        [InlineKeyboardButton(text="Статус сенсорів", callback_data=f"test:{locker_id}")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_main_menu")],
    ])


def f_locker_action_keyboard(locker_id, station_id) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔓 Відкрити", callback_data=f"f_adm_openLocker:{locker_id}")],
        [InlineKeyboardButton(text="🗓 Резервація", callback_data=f"f_adm_reserve:{locker_id}")],
        [InlineKeyboardButton(text="✅ Завершити оренду", callback_data=f"f_adm_close_rent:{locker_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"f_locker_status:{station_id}")],
    ])


# --- Error report ---

error_report_confirm_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="✅ Підтвердити", callback_data="confirm_problem")],
    [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel_problem")],
])

error_report_skip_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Пропустити", callback_data="skip_file")],
    [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel_problem")],
])


# --- Finish rent ---

finish_rent_cancel_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="❌ Скасувати", callback_data="finish_rent_cancel")],
])

rent_finish_confirm_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🔒 Кінець оренди", callback_data="confirm_rent_finish")],
    [InlineKeyboardButton(text="❌ Скасувати", callback_data="finish_rent_cancel")],
])


def topup_pay_menu(price_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Перейти до оплат", url=price_url)],
    ])

