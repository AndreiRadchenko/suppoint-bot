from aiogram import Bot, Dispatcher
from config_data.config import Config, load_config
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

storage = MemoryStorage()

config: Config = load_config()

bot = Bot(token=config.tg_bot.token, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher(storage=storage)
