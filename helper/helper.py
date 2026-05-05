from create_bot import bot
import logging
import asyncio
from zoneinfo import ZoneInfo
from datetime import datetime
from config_data.config import Config, load_config, SHIFT_CLOSE_START, SHIFT_CLOSE_END
from text.text import MSG_SHIFT_CLOSED
import aiohttp
config: Config = load_config()


def is_shift_closed() -> bool:
    """Return True when current Kyiv time falls within the configured maintenance window.

    Handles both same-day (start < end) and overnight (start > end) windows.
    When start == end the window is treated as never closed.
    """
    now = datetime.now(ZoneInfo('Europe/Kyiv')).time().replace(second=0, microsecond=0)
    if SHIFT_CLOSE_START == SHIFT_CLOSE_END:
        return False
    if SHIFT_CLOSE_END > SHIFT_CLOSE_START:  # same-day window, e.g. 02:00 – 06:00
        return SHIFT_CLOSE_START <= now < SHIFT_CLOSE_END
    # overnight window, e.g. 23:45 – 01:00 (or 23:45 – 00:00)
    return now >= SHIFT_CLOSE_START or now < SHIFT_CLOSE_END


def shift_closed_msg() -> str:
    """Return the localised maintenance message with actual configured times."""
    return MSG_SHIFT_CLOSED.format(
        start=SHIFT_CLOSE_START.strftime('%H:%M'),
        end=SHIFT_CLOSE_END.strftime('%H:%M'),
    )


def log_exception(e):
    logging.exception(e)
    pass


# async def clear_messages(chat_id, message_id, num_messages=10):
#     pass  # Message deletion disabled — preserve chat history

async def clear_messages(chat_id, message_id, num_messages=10):
    for i in range(num_messages):
        mid = message_id - i
        try:
            # edit_message_reply_markup raises if the message has no inline keyboard
            # (Telegram returns "message is not modified" or similar error).
            # So if this succeeds, the message had a keyboard — delete it.
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=mid, reply_markup=None)
            await bot.delete_message(chat_id, mid)
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