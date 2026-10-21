import logging
import io
from typing import Optional, List, Dict, Any
from aiogram import Bot, Dispatcher, types
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.enums import ParseMode

from app.core.config import settings

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    VIP & Free Channel Notification Engine built on Aiogram 3.x.
    Dispatches automated dark-mode signal cards and timelines to subscribers.
    """

    def __init__(self, bot_token: Optional[str] = None):
        self.bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self.bot: Optional[Bot] = None
        self.dp: Optional[Dispatcher] = None

        if self.bot_token and self.bot_token != "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ":
            self.bot = Bot(token=self.bot_token)
            self.dp = Dispatcher()

    def is_configured(self) -> bool:
        return self.bot is not None

    async def send_morning_calendar_alert(
        self,
        event_title: str,
        event_time_str: str,
        expected_pips: int = 1200,
        channel_id: Optional[str] = None,
    ) -> bool:
        """10:00 AM Daily Morning Briefing."""
        target_channel = channel_id or settings.TELEGRAM_VIP_CHANNEL_ID
        if not self.bot or not target_channel:
            logger.info(f"[Telegram Mock] Morning Alert: {event_title} at {event_time_str}")
            return False

        text = (
            f"☀️ **KUN TARTIBI: TIER-1 MAKRO YANGILIK!**\n\n"
            f"📅 Bugun soat **{event_time_str}** da bozorning eng kuchli yangiligi:\n"
            f"🔥 **{event_title}**\n\n"
            f"📊 **Kutilayotgan volatillik:** {expected_pips}+ punkt ({expected_pips // 10}+ pips)\n"
            f"🧠 **AI MacroSniper Pipeline:**\n"
            f"• 14:30 (T-3h): Fundamental AI tahlili\n"
            f"• 16:30 (T-1h): MT5 Likvidlik xaritasi (Order Blocklar)\n"
            f"• 17:28 (4:58): Aniq Limit va Stop orderlar (Signallar)\n"
            f"• 17:30:01: 1-soniyali tasdiq va Kill-Switch himoyasi\n\n"
            f"⚡ *Bildirishnomalarni yoqib qo'ying!*"
        )

        try:
            await self.bot.send_message(
                chat_id=target_channel,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram morning alert: {e}")
            return False

    async def send_t3h_macro_scan(
        self,
        event_title: str,
        macro_score: float,
        summary_text: str,
        channel_id: Optional[str] = None,
    ) -> bool:
        """14:30 T-3h Fundamental intelligence update."""
        target_channel = channel_id or settings.TELEGRAM_VIP_CHANNEL_ID
        if not self.bot or not target_channel:
            logger.info(f"[Telegram Mock] T-3h Macro Scan: Score {macro_score}")
            return False

        direction = "XAUUSD SELL (USD Kuchayadi)" if macro_score > 0 else "XAUUSD BUY (USD Kuchsizlanadi)"
        text = (
            f"🧠 **[T-3 SOAT OLDIN] AI MACRO SCAN YAKUNLANDI**\n\n"
            f"📊 Voqea: **{event_title}**\n"
            f"📈 AI Macro Score: **{macro_score:+0.1f} / 100**\n"
            f"🧭 Birlamchi kutilma: **{direction}**\n\n"
            f"{summary_text}\n\n"
            f"⏳ Navbatdagi bosqich: Soat 16:30 da MT5 Likvidlik va Order Block tahlili beriladi."
        )

        try:
            await self.bot.send_message(
                chat_id=target_channel,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send T-3h Telegram update: {e}")
            return False

    async def send_t1h_liquidity_map(
        self,
        event_title: str,
        upper_ob: float,
        lower_ob: float,
        summary_text: str,
        channel_id: Optional[str] = None,
    ) -> bool:
        """16:30 T-1h Liquidity mapping and Stop-Hunt trap alert."""
        target_channel = channel_id or settings.TELEGRAM_VIP_CHANNEL_ID
        if not self.bot or not target_channel:
            logger.info(f"[Telegram Mock] T-1h Liquidity: Upper OB={upper_ob}, Lower OB={lower_ob}")
            return False

        text = (
            f"📊 **[T-1 SOAT OLDIN] MT5 LIKVIDLIK VA STOP-HUNT XARITASI**\n\n"
            f"🎯 Voqea: **{event_title}**\n"
            f"🏛️ **Institutsional Buy-Side Likvidlik (Upper OB):** `{upper_ob:.2f}`\n"
            f"🏛️ **Institutsional Sell-Side Likvidlik (Lower OB):** `{lower_ob:.2f}`\n\n"
            f"{summary_text}\n\n"
            f"⚠️ *Diqqat:* Market-meykerlar aynan shu zonalardagi chakana treyderlar Stop-Loss'larini yig'ishga harakat qilishadi. "
            f"Soat **17:28 da (4:58)** aniq Limit Trap va Breakout Stop orderlar yuboriladi!"
        )

        try:
            await self.bot.send_message(
                chat_id=target_channel,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send T-1h Telegram update: {e}")
            return False

    async def send_458_sniper_signal(
        self,
        event_title: str,
        symbol: str,
        bias: str,
        confidence: int,
        limit_type: str,
        limit_price: float,
        limit_sl: float,
        limit_tp: float,
        stop_type: str,
        stop_price: float,
        stop_sl: float,
        stop_tp: float,
        card_image_bytes: Optional[io.BytesIO] = None,
        channel_id: Optional[str] = None,
    ) -> bool:
        """
        17:28 (4:58) Pre-Sniper Telegram VIP Signal with Dark-Mode Infographic Card.
        """
        target_channel = channel_id or settings.TELEGRAM_VIP_CHANNEL_ID
        caption = (
            f"🎯 **[4:58 PRE-SNIPER SIGNAL] — {symbol}**\n\n"
            f"📊 **Voqea:** {event_title}\n"
            f"🧭 **Asosiy Kutilma:** `{bias}` (Ishonch: **{confidence}%**)\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"1️⃣ **JUDAS SWING TRAP (LIMIT ORDER):**\n"
            f"• Buyruq: **{limit_type}** @ `{limit_price:.2f}`\n"
            f"• Stop-Loss: `{limit_sl:.2f}`\n"
            f"• Take-Profit: `{limit_tp:.2f}` *(+1200 pips)*\n\n"
            f"2️⃣ **MOMENTUM BREAKOUT (STOP ORDER):**\n"
            f"• Buyruq: **{stop_type}** @ `{stop_price:.2f}`\n"
            f"• Stop-Loss: `{stop_sl:.2f}`\n"
            f"• Take-Profit: `{stop_tp:.2f}` *(+1000 pips)*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ *Spred buferi kiritilgan. Soat 17:30:01 da Kill-Switch himoyasi ishga tushadi!*"
        )

        # Inline button keyboard for 1-click Mini App execution in VIP channel
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📱 MacroSniper Mini App",
                        url=settings.MINI_APP_URL,
                    )
                ]
            ]
        )

        if not self.bot or not target_channel:
            logger.info(f"[Telegram Mock] 4:58 Pre-Sniper Signal: {bias} Limit @ {limit_price}")
            return False

        try:
            if card_image_bytes:
                photo = BufferedInputFile(card_image_bytes.getvalue(), filename="pre_sniper_signal.png")
                await self.bot.send_photo(
                    chat_id=target_channel,
                    photo=photo,
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=keyboard,
                )
            else:
                await self.bot.send_message(
                    chat_id=target_channel,
                    text=caption,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=keyboard,
                )
            return True
        except Exception as e:
            logger.error(f"Failed to send 4:58 Sniper Signal: {e}")
            return False

    async def send_safety_instant_alert(
        self,
        event_title: str,
        is_confirmed: bool,
        actual: float,
        forecast: float,
        action_message: str,
        card_image_bytes: Optional[io.BytesIO] = None,
        channel_id: Optional[str] = None,
    ) -> bool:
        """
        17:30:01 Instant Verification or Kill-Switch emergency post.
        """
        target_channel = channel_id or settings.TELEGRAM_VIP_CHANNEL_ID
        headline = "✅ ACTUAL DATA CONFIRMED!" if is_confirmed else "🚨 DATA SHOCK — KILL-SWITCH TRIGGERED!"

        caption = (
            f"{headline}\n\n"
            f"📊 **{event_title}**\n"
            f"• Actual: `{actual}` | Forecast: `{forecast}` (Dev: `{actual - forecast:+0.2f}`)\n\n"
            f"{action_message}\n\n"
            f"⚡ *Bajarilish vaqti: 0.3 soniya*"
        )

        if not self.bot or not target_channel:
            logger.info(f"[Telegram Mock] 17:30:01 Safety Alert: {headline}")
            return False

        try:
            if card_image_bytes:
                photo = BufferedInputFile(card_image_bytes.getvalue(), filename="safety_alert.png")
                await self.bot.send_photo(
                    chat_id=target_channel,
                    photo=photo,
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN,
                )
            else:
                await self.bot.send_message(
                    chat_id=target_channel,
                    text=caption,
                    parse_mode=ParseMode.MARKDOWN,
                )
            return True
        except Exception as e:
            logger.error(f"Failed to send Safety Alert: {e}")
            return False


telegram_notifier = TelegramNotifier()
