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
admin_menu = InlineKeyboardMarkup(inline_keyboard=[
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