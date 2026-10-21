import logging
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.enums import ParseMode
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.user import User, SubscriptionTier
from app.models.event import EconomicEvent, SniperSignal
from app.core.config import settings

logger = logging.getLogger(__name__)

router = Router()


def get_main_keyboard() -> InlineKeyboardMarkup:
    mini_app_url = "https://macrosniper-ai.web.app"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📱 MacroSniper Mini Appni Ochish",
                    web_app=WebAppInfo(url=mini_app_url),
                )
            ],
            [
                InlineKeyboardButton(text="🎯 Bugungi Yangiliklar", callback_data="btn_events"),
                InlineKeyboardButton(text="⚡ Faol Signallar", callback_data="btn_signals"),
            ],
            [
                InlineKeyboardButton(text="💎 VIP Obuna Tizimi", callback_data="btn_vip"),
                InlineKeyboardButton(text="🤖 MT5 Auto-Copier", callback_data="btn_copier"),
            ],
        ]
    )


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or "Treyder"

    # Register user in DB if new
    async with AsyncSessionLocal() as session:
        query = select(User).where(User.telegram_id == user_id)
        res = await session.execute(query)
        user = res.scalar_one_or_none()

        if not user:
            user = User(
                telegram_id=user_id,
                username=username,
                first_name=first_name,
                tier=SubscriptionTier.FREE,
            )
            session.add(user)
            await session.commit()

    welcome_text = (
        f"🎯 **Xush kelibsiz, {first_name}!**\n\n"
        f"**MacroSniper AI** — Forex bozoridagi eng kuchli fundamental yangiliklar "
        f"(**FOMC, CPI, NFP, PPI**) paytidagi 500–2000 punktlik trendlarni "
        f"yangilikdan 2 daqiqa oldin (**4:58 Pre-Sniper Trap**) va real vaqtda (**5:00:01 Kill-Switch**) "
        f"ushlab beruvchi algoritmik platforma.\n\n"
        f"🧠 **Bizning 4 Bosqichli Algoritm:**\n"
        f"1️⃣ **T-3h:** Fundamental Engine (ADP, ISM, PPI tahlili)\n"
        f"2️⃣ **T-1h:** MT5 Likvidlik va Order Block xaritasi\n"
        f"3️⃣ **T-2m (4:58):** Judas Swing Limit Trap + Breakout Stop\n"
        f"4️⃣ **5:00:01:** Ultra-Past Kechikishli Kill-Switch va Ovozli AI\n\n"
        f"Quyidagi tugmalar orqali platformani boshqaring:"
    )

    await message.answer(welcome_text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())


@router.message(Command("events"))
@router.callback_query(F.data == "btn_events")
async def cmd_events(event_obj: types.Message | types.CallbackQuery):
    message = event_obj if isinstance(event_obj, types.Message) else event_obj.message

    async with AsyncSessionLocal() as session:
        q = select(EconomicEvent).order_by(EconomicEvent.event_time.asc()).limit(10)
        res = await session.execute(q)
        events = res.scalars().all()

    if not events:
        text = "📅 **Bugun uchun rejalashtirilgan Tier-1 qizil yangiliklar topilmadi.**"
    else:
        text = "📅 **BUGUNGI TIER-1 MAKRO YANGILIKLAR PIPELINE:**\n\n"
        for ev in events:
            time_str = ev.event_time.strftime("%H:%M UTC")
            state_emoji = {
                "SCHEDULED": "⏳",
                "MACRO_ANALYZED": "🧠",
                "LIQUIDITY_MAPPED": "📊",
                "TRAP_DEPLOYED": "🎯",
                "LIVE_MONITORING": "⚡",
                "DATA_CONFIRMED": "✅",
                "SAFETY_TRIGGERED": "🚨",
            }.get(ev.state.value, "📌")

            text += (
                f"{state_emoji} **{ev.title}**\n"
                f"• Vaqti: `{time_str}` | Valyuta: `{ev.currency}`\n"
                f"• Holat: `{ev.state.value}` | Total Score: `{ev.total_score:+0.1f}`\n\n"
            )

    if isinstance(event_obj, types.CallbackQuery):
        await event_obj.answer()
        await message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())
    else:
        await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())


@router.message(Command("signals"))
@router.callback_query(F.data == "btn_signals")
async def cmd_signals(event_obj: types.Message | types.CallbackQuery):
    message = event_obj if isinstance(event_obj, types.Message) else event_obj.message

    async with AsyncSessionLocal() as session:
        q = select(SniperSignal).order_by(SniperSignal.id.desc()).limit(1)
        res = await session.execute(q)
        signal = res.scalar_one_or_none()

    if not signal:
        text = "⚡ **Hozirda faol pre-sniper signallari mavjud emas.** Yangilikka 2 daqiqa qolganda avtomatik e'lon qilinadi."
    else:
        text = (
            f"🎯 **SO'NGGI SNIPER SIGNAL — {signal.symbol}**\n\n"
            f"🧭 **Kutilma:** `{signal.bias}` (Ishonch: **{signal.confidence}%**)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"1️⃣ **JUDAS SWING TRAP:**\n"
            f"• `{signal.limit_trap_type}` @ `{signal.limit_trap_price:.2f}`\n"
            f"• SL: `{signal.limit_sl:.2f}` | TP: `{signal.limit_tp:.2f}`\n\n"
            f"2️⃣ **MOMENTUM BREAKOUT:**\n"
            f"• `{signal.stop_break_type}` @ `{signal.stop_break_price:.2f}`\n"
            f"• SL: `{signal.stop_sl:.2f}` | TP: `{signal.stop_tp:.2f}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Holat: `{signal.status}` | Kill-Switch: `{signal.is_kill_switch_triggered}`"
        )

    if isinstance(event_obj, types.CallbackQuery):
        await event_obj.answer()
        await message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())
    else:
        await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())


@router.message(Command("vip"))
@router.callback_query(F.data == "btn_vip")
async def cmd_vip(event_obj: types.Message | types.CallbackQuery):
    message = event_obj if isinstance(event_obj, types.Message) else event_obj.message

    text = (
        f"💎 **MACRO SNIPER AI — OBUNA TARIFLARI**\n\n"
        f"1️⃣ **FREE TIER (BEPUL):**\n"
        f"• 10:00 Kunlik anonslar\n"
        f"• Yangilikdan 5 daqiqa keyingi natijalar hisoboti\n\n"
        f"2️⃣ **VIP PRO (\$79 / oy):**\n"
        f"• 14:30 T-3h Fundamental AI skaner\n"
        f"• 16:30 T-1h MT5 Likvidlik xaritasi\n"
        f"• **17:28 (4:58) Aniq Limit/Stop Orderlar** (Dark Mode rasm bilan)\n"
        f"• 5:00:01 Ultra-Fast Kill-Switch himoyasi\n\n"
        f"3️⃣ **HEDGE FUND / AUTO-COPIER (\$199 / oy):**\n"
        f"• VIP PRO ning barcha imkoniyatlari\n"
        f"• MT5 ga 0.2 soniyada avtomatik order ochish (Auto-Bridge)\n"
        f"• Live FOMC Speech Audio AI signallari\n\n"
        f"💳 Obunani faollashtirish uchun: @MacroSniperAdmin ga murojaat qiling."
    )

    if isinstance(event_obj, types.CallbackQuery):
        await event_obj.answer()
        await message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())
    else:
        await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())


@router.message(Command("copier"))
@router.callback_query(F.data == "btn_copier")
async def cmd_copier(event_obj: types.Message | types.CallbackQuery):
    message = event_obj if isinstance(event_obj, types.Message) else event_obj.message

    text = (
        f"🤖 **METATRADER 5 AUTO-COPIER BRIDGE**\n\n"
        f"Siz signallarni qo'lda kiritishga ulgurmaysizmi? "
        f"Bizning Auto-Copierimiz yangilik chiqishidan 2 daqiqa oldin buyruqlarni "
        f"to'g'ridan-to'g'ri MetaTrader 5 hisobingizga avtomatik joylashtiradi.\n\n"
        f"⚙️ **Status:** `SIMULATION_ONLINE`\n"
        f"⚡ **Kechikish (Execution Latency):** `< 180 ms`\n"
        f"🛡️ **Kill-Switch Auto-Cancel:** `FAOL`\n\n"
        f"Hisobingizni ulash uchun Mini App orqali MT5 login va serveringizni kiriting."
    )

    if isinstance(event_obj, types.CallbackQuery):
        await event_obj.answer()
        await message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())
    else:
        await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())
