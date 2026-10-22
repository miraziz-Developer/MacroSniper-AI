import logging
from datetime import timedelta
from html import escape

from aiogram import F, Router, types
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, WebAppInfo
from sqlalchemy import func, select

from app.billing.subscriptions import (
    VIP_PAYLOAD, extend_vip, get_or_create_user, record_payment, redeem_promo, revoke_vip,
)
from app.core.config import settings
from app.core.db import SessionLocal
from app.models import Event, EventState, Payment, Plan, User, utcnow
from app.pipeline import orchestrator
from app.signals import history
from app.telegram import texts

logger = logging.getLogger(__name__)
router = Router()


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Mini App", web_app=WebAppInfo(url=settings.MINI_APP_URL))],
            [
                InlineKeyboardButton(text="📅 Yangiliklar", callback_data="events"),
                InlineKeyboardButton(text="🎯 Reja", callback_data="plan"),
                InlineKeyboardButton(text="🧾 Natijalar", callback_data="results"),
            ],
            [InlineKeyboardButton(text=f"💎 VIP — {settings.VIP_PRICE_STARS} ⭐", callback_data="vip")],
        ]
    )


async def _user(tg: types.User) -> User:
    async with SessionLocal() as session:
        return await get_or_create_user(session, tg.id, tg.username, tg.first_name)


def _is_admin(obj: types.Message) -> bool:
    return bool(obj.from_user) and obj.from_user.id in settings.admin_ids


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user = await _user(message.from_user)
    await message.answer(
        texts.welcome_message(message.from_user.first_name or "Treyder", user.is_vip(), user.vip_until),
        reply_markup=main_keyboard(),
    )


async def _events_text(admin: bool) -> str:
    async with SessionLocal() as session:
        rows = await session.execute(
            select(Event)
            .where(Event.event_time >= utcnow() - timedelta(hours=1), Event.event_time <= utcnow() + timedelta(days=7))
            .order_by(Event.event_time)
            .limit(12)
        )
        events = rows.scalars().all()
    if not events:
        return "📅 Yaqin 7 kunda AQSH bo'yicha muhim yangilik yo'q."
    lines = ["📅 <b>AQSH yuqori ta'sirli yangiliklari</b>\n"]
    for ev in events:
        tag = " · 🎯 VIP reja" if history.is_plannable(ev.title) else ""
        prefix = f"#{ev.id} " if admin else ""
        lines.append(f"{prefix}{texts.event_line(ev)}{tag}\n")
    return "\n".join(lines)


@router.message(Command("events"))
async def cmd_events(message: types.Message):
    await message.answer(await _events_text(_is_admin(message)), reply_markup=main_keyboard())


async def _plan_text(user: User) -> str:
    if not user.is_vip():
        return f"🔒 Savdo rejalari faqat VIP uchun. /vip — {settings.VIP_PRICE_STARS} ⭐ / {settings.VIP_DAYS} kun."
    async with SessionLocal() as session:
        row = (
            await session.execute(
                select(Plan, Event)
                .join(Event, Plan.event_id == Event.id)
                .where(Event.event_time >= utcnow() - timedelta(hours=6))
                .order_by(Plan.id.desc())
                .limit(1)
            )
        ).first()
    if row is None:
        return "🎯 Hozir faol reja yo'q. Reja yangilikdan 2 daqiqa oldin avtomatik keladi."
    plan, ev = row
    return texts.outcome_message(ev) if ev.state == EventState.RESOLVED else texts.plan_message(ev, plan)


@router.message(Command("plan"))
async def cmd_plan(message: types.Message):
    await message.answer(await _plan_text(await _user(message.from_user)), reply_markup=main_keyboard())


async def _results_text() -> str:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(Plan, Event).join(Event, Plan.event_id == Event.id)
                .where(Plan.result_r.is_not(None)).order_by(Event.event_time.desc()).limit(10)
            )
        ).all()
    if not rows:
        return "🧾 Hali baholangan reja yo'q. Har reja yangilikdan 2 soat o'tib avtomatik hisoblanadi."
    lines = ["🧾 <b>So'nggi rejalar natijasi</b> (1R = stop-loss masofasi)\n"]
    for plan, ev in rows:
        lines.append(f"{texts.tashkent_time(ev.event_time)} · {escape(ev.title)}: <b>{plan.result_r:+.2f}R</b>")
    lines.append(f"\nJami: <b>{sum(p.result_r for p, _ in rows):+.2f}R</b>")
    return "\n".join(lines)


@router.message(Command("results"))
async def cmd_results(message: types.Message):
    await message.answer(await _results_text(), reply_markup=main_keyboard())


@router.message(Command("status"))
async def cmd_status(message: types.Message):
    user = await _user(message.from_user)
    if user.is_vip():
        text = f"💎 VIP faol: {texts.tashkent_time(user.vip_until)} (Toshkent) gacha."
    else:
        text = "Holat: FREE. VIP olish: /vip"
    await message.answer(text)


async def send_vip_invoice(chat_id: int, bot) -> None:
    await bot.send_invoice(
        chat_id=chat_id,
        title=f"MacroSniper VIP — {settings.VIP_DAYS} kun",
        description="XAUUSD savdo rejalari, kontekst tahlili va natija xabarlari (AQSH Tier-1 yangiliklari).",
        payload=VIP_PAYLOAD,
        currency="XTR",
        prices=[LabeledPrice(label="VIP", amount=settings.VIP_PRICE_STARS)],
    )


@router.message(Command("vip"))
async def cmd_vip(message: types.Message):
    await send_vip_invoice(message.chat.id, message.bot)


@router.callback_query(F.data.in_({"events", "plan", "results", "vip"}))
async def on_button(cb: types.CallbackQuery):
    await cb.answer()
    if cb.data == "vip":
        await send_vip_invoice(cb.message.chat.id, cb.bot)
    elif cb.data == "results":
        await cb.message.answer(await _results_text(), reply_markup=main_keyboard())
    elif cb.data == "events":
        await cb.message.answer(await _events_text(cb.from_user.id in settings.admin_ids), reply_markup=main_keyboard())
    else:
        await cb.message.answer(await _plan_text(await _user(cb.from_user)), reply_markup=main_keyboard())


@router.pre_checkout_query()
async def on_pre_checkout(query: types.PreCheckoutQuery):
    ok = (
        query.invoice_payload == VIP_PAYLOAD
        and query.currency == "XTR"
        and query.total_amount == settings.VIP_PRICE_STARS
    )
    await query.answer(ok=ok, error_message=None if ok else "Narx o'zgargan, /vip ni qayta bosing.")


@router.message(F.successful_payment)
async def on_paid(message: types.Message):
    pay = message.successful_payment
    async with SessionLocal() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.username)
        credited = await record_payment(
            session, user, pay.telegram_payment_charge_id, pay.total_amount, settings.VIP_DAYS
        )
        user = await session.get(User, user.id)
    if credited:
        logger.info("VIP payment %s from %s", pay.telegram_payment_charge_id, message.from_user.id)
        await message.answer(f"✅ Rahmat! VIP {texts.tashkent_time(user.vip_until)} gacha faol.")


@router.message(Command("promo"))
async def cmd_promo(message: types.Message, command: CommandObject):
    if not command.args:
        await message.answer("Foydalanish: /promo KOD")
        return
    async with SessionLocal() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.username)
        result = await redeem_promo(session, user, command.args)
        user = await session.get(User, user.id)
    await message.answer({
        "ok": f"🎁 Tabriklaymiz! {settings.PROMO_DAYS} kunlik bepul VIP {texts.tashkent_time(user.vip_until)} gacha faol.",
        "used": "Bu promo-koddan allaqachon foydalangansiz.",
        "exhausted": "Afsuski, bu promo-kodning barcha joylari band bo'lgan.",
        "invalid": "Promo-kod noto'g'ri.",
    }[result])


@router.message(Command("paysupport"))
async def cmd_paysupport(message: types.Message):
    await message.answer(
        "To'lov bo'yicha savol yoki qaytarish so'rovi uchun shu chatga yozing — admin javob beradi. "
        "Telegram Stars to'lovlari Telegram qoidalari asosida ko'rib chiqiladi."
    )


# ---------------- Admin ----------------


@router.message(Command("stats"), F.func(_is_admin))
async def cmd_stats(message: types.Message):
    async with SessionLocal() as session:
        users = await session.scalar(select(func.count(User.id)))
        vips = await session.scalar(select(func.count(User.id)).where(User.vip_until > utcnow()))
        stars = await session.scalar(select(func.coalesce(func.sum(Payment.stars), 0)))
        upcoming = await session.scalar(
            select(func.count(Event.id)).where(Event.event_time > utcnow(), Event.state != EventState.SKIPPED)
        )
    await message.answer(
        f"👥 Foydalanuvchilar: {users}\n💎 Faol VIP: {vips}\n⭐ Jami Stars: {stars}\n📅 Rejali yangiliklar: {upcoming}"
    )


def _parse_args(command: CommandObject, count: int):
    parts = (command.args or "").split()
    return parts if len(parts) == count else None


@router.message(Command("grant"), F.func(_is_admin))
async def cmd_grant(message: types.Message, command: CommandObject):
    args = _parse_args(command, 2)
    if not args or not args[0].isdigit() or not args[1].isdigit():
        await message.answer("Foydalanish: /grant TELEGRAM_ID KUN")
        return
    async with SessionLocal() as session:
        user = await get_or_create_user(session, int(args[0]))
        await extend_vip(session, user, int(args[1]))
    await message.answer(f"✅ {args[0]} uchun VIP {texts.tashkent_time(user.vip_until)} gacha.")


@router.message(Command("revoke"), F.func(_is_admin))
async def cmd_revoke(message: types.Message, command: CommandObject):
    args = _parse_args(command, 1)
    if not args or not args[0].isdigit():
        await message.answer("Foydalanish: /revoke TELEGRAM_ID")
        return
    async with SessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == int(args[0])))).scalar_one_or_none()
        if user:
            await revoke_vip(session, user)
    await message.answer("✅ Bekor qilindi." if user else "Foydalanuvchi topilmadi.")


@router.message(Command("actual"), F.func(_is_admin))
async def cmd_actual(message: types.Message, command: CommandObject):
    args = _parse_args(command, 2)
    try:
        event_id, value = int(args[0]), float(args[1].replace(",", ".").rstrip("%KkMmBb"))
    except (TypeError, ValueError):
        await message.answer("Foydalanish: /actual EVENT_ID QIYMAT  (ID lar: /events)")
        return
    done = await orchestrator.resolve_event(event_id, value, f"admin {message.from_user.id}")
    if not done:
        await message.answer("Bu yangilik topilmadi yoki allaqachon yakunlangan.")
