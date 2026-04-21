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
    mono_receipt_email_fallback: str
    checkbox_enabled: bool
    checkbox_mode: str
    checkbox_api_base_url: str
    checkbox_license_key: str
    checkbox_test_token: str
    checkbox_live_token: str
    checkbox_api_token: str
    checkbox_sell_endpoint: str
    checkbox_status_endpoint: str
    checkbox_open_shift_endpoint: str
    checkbox_close_shift_endpoint: str
    checkbox_go_offline_endpoint: str
    checkbox_open_shift_payload: str
    checkbox_close_shift_payload: str
    checkbox_go_offline_payload: str
    checkbox_shift_timezone: str
    checkbox_shift_auto_close_time: str
    checkbox_shift_fiscal_code_prefix: str
    checkbox_request_timeout_sec: int
    checkbox_receipt_url_template: str
    fiscal_retry_interval_sec: int
    fiscal_retry_window_min: int


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
            ha_url=env.str('HA_URL', default=''),
            ha_token=env.str('HA_TOKEN', default=''),
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
            mono_receipt_email_fallback=env.str('MONO_RECEIPT_EMAIL_FALLBACK', default=''),
            checkbox_enabled=env.bool('CHECKBOX_ENABLED', default=False),
            checkbox_mode=env.str('CHECKBOX_MODE', default='test').lower(),
            checkbox_api_base_url=env.str('CHECKBOX_API_BASE_URL', default='https://api.checkbox.in.ua'),
            checkbox_license_key=env.str('CHECKBOX_LICENSE_KEY', default=''),
            checkbox_test_token=env.str('CHECKBOX_TEST_TOKEN', default=''),
            checkbox_live_token=env.str('CHECKBOX_LIVE_TOKEN', default=''),
            checkbox_api_token=env.str('CHECKBOX_API_TOKEN', default=''),
            checkbox_sell_endpoint=env.str('CHECKBOX_SELL_ENDPOINT', default='/api/v1/receipts/sell'),
            checkbox_status_endpoint=env.str('CHECKBOX_STATUS_ENDPOINT', default='/api/v1/receipts/{receipt_id}'),
            checkbox_open_shift_endpoint=env.str('CHECKBOX_OPEN_SHIFT_ENDPOINT', default='/api/v1/shifts'),
            checkbox_close_shift_endpoint=env.str('CHECKBOX_CLOSE_SHIFT_ENDPOINT', default='/api/v1/shifts/close'),
            checkbox_go_offline_endpoint=env.str('CHECKBOX_GO_OFFLINE_ENDPOINT', default='/api/v1/cash-registers/go-offline'),
            checkbox_open_shift_payload=env.str('CHECKBOX_OPEN_SHIFT_PAYLOAD', default='{}'),
            checkbox_close_shift_payload=env.str('CHECKBOX_CLOSE_SHIFT_PAYLOAD', default='{}'),
            checkbox_go_offline_payload=env.str('CHECKBOX_GO_OFFLINE_PAYLOAD', default='{}'),
            checkbox_shift_timezone=env.str('CHECKBOX_SHIFT_TIMEZONE', default='Europe/Kyiv'),
            checkbox_shift_auto_close_time=env.str('CHECKBOX_SHIFT_AUTO_CLOSE_TIME', default='23:45'),
            checkbox_shift_fiscal_code_prefix=env.str('CHECKBOX_SHIFT_FISCAL_CODE_PREFIX', default='AUTO'),
            checkbox_request_timeout_sec=env.int('CHECKBOX_REQUEST_TIMEOUT_SEC', default=20),
            checkbox_receipt_url_template=env.str('CHECKBOX_RECEIPT_URL_TEMPLATE', default='https://check.checkbox.ua/{receipt_id}/html'),
            fiscal_retry_interval_sec=env.int('FISCAL_RETRY_INTERVAL_SEC', default=60),
            fiscal_retry_window_min=env.int('FISCAL_RETRY_WINDOW_MIN', default=15),
        ),
    )
