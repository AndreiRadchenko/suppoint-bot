from db import Database
from create_bot import bot
from helper.helper import log_exception
from config_data.config import Config, load_config

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
                                                            '💳 Автоматично буде нарахована доплата згідно з чинним тарифом\n')
                            db.valid_until_down(rent[0])
                        else:
                            db.valid_until_down(rent[0])
                except Exception as e:
                    log_exception(e)
        else:
            pass
    except Exception as e:
        log_exception(e)
