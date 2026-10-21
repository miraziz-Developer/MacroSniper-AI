import asyncio
import logging
from aiogram import Bot, Dispatcher
from app.core.config import settings
from app.core.database import init_db
from app.services.bot_handlers import router as bot_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("MacroSniperBot")


async def run_bot():
    """Runs the Telegram Bot polling daemon."""
    await init_db()

    token = settings.TELEGRAM_BOT_TOKEN
    if not token or token == "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ":
        logger.warning("TELEGRAM_BOT_TOKEN is not set. Bot polling will not start. (Set in .env)")
        return

    bot = Bot(token=token)
    dp = Dispatcher()
    dp.include_router(bot_router)

    logger.info("MacroSniper Telegram Bot started polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run_bot())
