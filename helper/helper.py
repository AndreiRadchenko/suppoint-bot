from create_bot import bot
import logging
import asyncio
from config_data.config import Config, load_config
import aiohttp
config: Config = load_config()


def log_exception(e):
    logging.exception(e)
    pass


async def clear_messages(chat_id, message_id, num_messages=10):
    for i in range(num_messages):
        try:
            await bot.delete_message(chat_id, message_id - i)
        except Exception:
            pass


async def get_entity_state(entity_id: str, url: str, token: str):
    api_url = f"{url}/api/states/{entity_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    timeout = aiohttp.ClientTimeout(total=6, sock_connect=4, sock_read=4)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(api_url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("state")
                logging.warning("HA state request failed for %s with status %s", entity_id, response.status)
                return None
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logging.warning("HA state request error for %s: %s", entity_id, exc)
        return None
    except Exception as exc:
        logging.exception("Unexpected HA state request error for %s: %s", entity_id, exc)
        return None