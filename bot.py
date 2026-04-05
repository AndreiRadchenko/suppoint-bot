import asyncio
from create_bot import dp, bot
import logging
from handlers import rent, req, finishRent, start, error_report
from config_data.config import Config, load_config
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from services.payments import PaymentService, MonobankWebhookServer

from helper.utilits_funk import timer

config: Config = load_config()

logger = logging.getLogger(__name__)
payment_service = PaymentService()
webhook_server = MonobankWebhookServer(payment_service)


async def scheduler_funk():
# Створюємо планувальник
    scheduler = AsyncIOScheduler()
#
    scheduler.add_job(timer, trigger="interval", seconds=15)

#     # Запускаємо планувальник
    scheduler.start()


async def webhook_funk():
    await webhook_server.start()
    logger.info('MONOBANK WEBHOOK SERVER ON-LINE')
    while True:
        await asyncio.sleep(3600)


# Основна логіка бота
async def bot_funk():
    logging.basicConfig(
        level=logging.INFO,
        format='%(filename)s:%(lineno)d #%(levelname)-8s '
               '[%(asctime)s] - %(name)s - %(message)s')

    dp.include_router(rent.router)
    dp.include_router(finishRent.router)
    dp.include_router(req.router)
    dp.include_router(error_report.router)
    dp.include_router(start.router)

    logger.info('BOT ON-LINE')
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, skip_updates=True)


# Основна точка запуску всіх завдань
async def main():
    task1 = asyncio.create_task(bot_funk())
    task2 = asyncio.create_task(scheduler_funk())
    task3 = asyncio.create_task(webhook_funk())
    await asyncio.gather(task1, task2, task3)


if __name__ == '__main__':
    asyncio.run(main())
