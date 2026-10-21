import logging
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.core.config import settings

logger = logging.getLogger(__name__)

_bot: Optional[Bot] = None


def get_bot() -> Optional[Bot]:
    """Shared Bot instance (HTML parse mode); None when no token is configured."""
    global _bot
    if _bot is None and settings.bot_enabled:
        _bot = Bot(settings.TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    return _bot


async def run_polling() -> None:
    bot = get_bot()
    if bot is None:
        logger.warning("TELEGRAM_BOT_TOKEN not set — bot disabled.")
        return
    from app.telegram.handlers import router

    dp = Dispatcher()
    dp.include_router(router)
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot, handle_signals=False)
    except Exception:
        # Runs as a background task inside the web app; without this the crash would be silent
        logger.exception("Telegram polling crashed")
    finally:
        await bot.session.close()
