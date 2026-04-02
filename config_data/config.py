from dataclasses import dataclass
from environs import Env


@dataclass
class TgBot:
    token: str
    admin_ids: list[int]
    ha_url: str
    ha_token: str


@dataclass
class DatabaseConfig:
    path: str


@dataclass
class PaymentConfig:
    payer_name: str
    iban: str
    edrpou: str
    purpose: str


@dataclass
class Config:
    tg_bot: TgBot
    db: DatabaseConfig
    payment: PaymentConfig


def load_config(path: str | None = None) -> Config:
    env = Env()
    env.read_env(path)
    return Config(
        tg_bot=TgBot(
            token=env('BOT_TOKEN'),
            admin_ids=list(map(int, env.list('ADMINS'))),
            ha_url=env('HA_URL'),
            ha_token=env('HA_TOKEN'),
        ),
        db=DatabaseConfig(
            path=env('DB_PATH'),
        ),
        payment=PaymentConfig(
            payer_name=env('PAYMENT_PAYER_NAME'),
            iban=env('PAYMENT_IBAN'),
            edrpou=env('PAYMENT_EDRPOU'),
            purpose=env('PAYMENT_PURPOSE'),
        ),
    )
