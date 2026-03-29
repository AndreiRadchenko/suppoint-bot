from dataclasses import dataclass
from environs import Env


@dataclass
class TgBot:
    token: str
    admin_ids: list[int]
    ha_url: str
    ha_token: str


@dataclass
class Config:
    tg_bot: TgBot


def load_config(path: str | None = None) -> Config:
    env = Env()
    env.read_env(path)
    return Config(
        tg_bot=TgBot(
            token=env('BOT_TOKEN'),
            admin_ids=list(map(int, env.list('ADMINS'))),
            ha_url=env('HA_URL'),
            ha_token=env('HA_TOKEN'),
        )
    )
