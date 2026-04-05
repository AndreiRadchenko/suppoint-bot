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
    mono_test_token: str
    mono_live_token: str
    mono_mode: str
    mono_webhook_host: str
    mono_webhook_port: int
    mono_webhook_path: str
    mono_webhook_public_base: str
    mono_redirect_url: str
    mono_pubkey_cache_ttl: int


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
            mono_test_token=env.str('MONO_TEST_TOKEN', default=''),
            mono_live_token=env.str('MONO_LIVE_TOKEN', default=''),
            mono_mode=env.str('MONO_MODE', default='test'),
            mono_webhook_host=env.str('MONO_WEBHOOK_HOST', default='0.0.0.0'),
            mono_webhook_port=env.int('MONO_WEBHOOK_PORT', default=8080),
            mono_webhook_path=env.str('MONO_WEBHOOK_PATH', default='/webhooks/monobank'),
            mono_webhook_public_base=env.str('MONO_WEBHOOK_PUBLIC_BASE', default=''),
            mono_redirect_url=env.str('MONO_REDIRECT_URL', default='https://t.me'),
            mono_pubkey_cache_ttl=env.int('MONO_PUBKEY_CACHE_TTL', default=3600),
        ),
    )
