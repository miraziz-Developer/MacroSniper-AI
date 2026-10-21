import asyncio
import logging
from typing import Iterable, Optional

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import update

from app.core.config import settings
from app.core.db import SessionLocal
from app.models import User
from app.telegram.bot import get_bot

logger = logging.getLogger(__name__)


async def _send(chat_id, text: str, keyboard: Optional[InlineKeyboardMarkup] = None) -> bool:
    bot = get_bot()
    if bot is None:
        logger.info("[telegram disabled] -> %s: %s", chat_id, text[:120].replace("\n", " "))
        return False
    for _ in range(2):
        try:
            await bot.send_message(chat_id, text, reply_markup=keyboard, disable_web_page_preview=True)
            return True
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except TelegramForbiddenError:
            if isinstance(chat_id, int) and chat_id > 0:
                async with SessionLocal() as session:
                    await session.execute(update(User).where(User.telegram_id == chat_id).values(blocked_bot=True))
                    await session.commit()
            return False
        except Exception:
            logger.exception("Telegram send failed to %s", chat_id)
            return False
    return False


async def send_many(chat_ids: Iterable[int], text: str, keyboard: Optional[InlineKeyboardMarkup] = None) -> int:
    sent = 0
    for chat_id in chat_ids:
        sent += await _send(chat_id, text, keyboard)
        await asyncio.sleep(0.05)  # stay well under Telegram's ~30 msg/s limit
    return sent


async def send_channel(text: str, keyboard: Optional[InlineKeyboardMarkup] = None) -> bool:
    if not settings.TELEGRAM_CHANNEL_ID:
        return False
    return await _send(settings.TELEGRAM_CHANNEL_ID, text, keyboard)


async def send_admins(text: str) -> int:
    return await send_many(settings.admin_ids, text)
