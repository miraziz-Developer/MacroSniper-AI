"""All user-facing Telegram texts (HTML parse mode, Uzbek)."""

from datetime import datetime, timedelta, timezone
from html import escape
from typing import Optional

from app.models import Event, Plan
from app.signals.context import Context

TASHKENT = timezone(timedelta(hours=5))
RISK_NOTE = "<i>⚠️ Bu moliyaviy maslahat emas. Riskni o'zingiz boshqaring: bitta savdoda balansning 1–2% idan ko'p tavakkal qilmang.</i>"

SIDE_UZ = {"BUY": "🟢 BUY (oltin ko'tariladi)", "SELL": "🔴 SELL (oltin tushadi)", "INLINE": "⚪ Prognozga mos"}


def tashkent_time(dt: datetime) -> str:
    return dt.astimezone(TASHKENT).strftime("%d.%m %H:%M")


def _fmt(v: Optional[float], unit: Optional[str]) -> str:
    return "—" if v is None else f"{v:g}{unit or ''}"


def event_line(ev: Event) -> str:
    return (
        f"<b>{escape(ev.title)}</b>\n"
        f"🕒 {tashkent_time(ev.event_time)} (Toshkent) · Prognoz: {_fmt(ev.forecast, ev.unit)} · Avvalgi: {_fmt(ev.previous, ev.unit)}"
    )


def context_message(ev: Event, ctx: Context) -> str:
    bias = {"BUY": "🟢 Oltin uchun BUY tomonga moyil", "SELL": "🔴 Oltin uchun SELL tomonga moyil"}.get(
        ctx.bias, "⚪ Aniq yo'nalish yo'q — faqat breakout rejasi"
    )
    reasons = "\n".join(f"• {escape(r)}" for r in ctx.reasons)
    return (
        f"🧭 <b>3 soat qoldi — bozor konteksti</b>\n\n{event_line(ev)}\n\n"
        f"{bias} (ball: {ctx.gold_score:+.0f}/100)\n{reasons}\n\n"
        f"Savdo rejasi yangilikdan 2 daqiqa oldin yuboriladi."
    )


def _side_block(title: str, entry: float, sl: float, tp1: float, tp2: float, price: float) -> str:
    return (
        f"<b>{title}</b> <code>{entry:.2f}</code> (narxdan {entry - price:+.2f}$)\n"
        f"   SL <code>{sl:.2f}</code> · TP1 <code>{tp1:.2f}</code> · TP2 <code>{tp2:.2f}</code>"
    )


def plan_message(ev: Event, plan: Plan) -> str:
    if plan.primary:
        head = f"Asosiy tomon: {SIDE_UZ[plan.primary]} — teskari order himoya uchun."
    else:
        head = "Yo'nalish noaniq: ikkala order ham qo'yiladi, qaysi biri ochilsa, ikkinchisini bekor qiling."
    return (
        f"🎯 <b>XAUUSD SAVDO REJASI — 2 daqiqa qoldi</b>\n\n{event_line(ev)}\n\n"
        f"Joriy narx: <code>{plan.price:.2f}</code> ({escape(plan.price_source)}) · ATR(15m): {plan.atr:.2f}$\n"
        f"Yangilik oldi diapazoni: {plan.range_low:.2f} – {plan.range_high:.2f}\n\n"
        f"{_side_block('BUY STOP', plan.buy_entry, plan.buy_sl, plan.buy_tp1, plan.buy_tp2, plan.price)}\n"
        f"{_side_block('SELL STOP', plan.sell_entry, plan.sell_sl, plan.sell_tp1, plan.sell_tp2, plan.price)}\n\n"
        f"{head}\n"
        f"TP1 da yarmini yoping va SL ni kirish narxiga o'tkazing.\n"
        f"Brokeringiz narxi farq qilsa, qavs ichidagi masofalardan foydalaning.\n\n{RISK_NOTE}"
    )


def outcome_message(ev: Event) -> str:
    side = SIDE_UZ.get(ev.outcome or "INLINE", "")
    if ev.outcome == "INLINE":
        action = "Kuchli impuls kutilmaydi — ochilmagan orderlarni bekor qilish tavsiya etiladi."
    else:
        keep = "BUY STOP" if ev.outcome == "BUY" else "SELL STOP"
        drop = "SELL STOP" if ev.outcome == "BUY" else "BUY STOP"
        action = f"{keep} saqlanadi, {drop} bekor qilinadi."
    return (
        f"⚡ <b>NATIJA CHIQDI</b>\n\n{event_line(ev)}\n"
        f"Fakt: <b>{_fmt(ev.actual, ev.unit)}</b>\n\n{side}\n{action}"
    )


def teaser_message(ev: Event) -> str:
    return (
        f"🎯 {event_line(ev)}\n\n"
        f"XAUUSD savdo rejasi VIP obunachilarga yuborildi. Obuna: botdagi /vip buyrug'i."
    )


def welcome_message(first_name: str, is_vip: bool, vip_until: Optional[datetime]) -> str:
    status = (
        f"💎 VIP faol: {tashkent_time(vip_until)} gacha" if is_vip and vip_until else "Holat: FREE (bepul)"
    )
    return (
        f"Assalomu alaykum, <b>{escape(first_name)}</b>!\n\n"
        f"<b>MacroSniper</b> — AQSH makro yangiliklari (CPI, NFP, FOMC, Claims…) paytida XAUUSD uchun "
        f"haqiqiy bozor ma'lumotiga asoslangan savdo rejasini beradi:\n"
        f"• 3 soat oldin — DXY, obligatsiyalar va prognoz bo'yicha kontekst\n"
        f"• 2 daqiqa oldin — ATR va diapazon asosida BUY STOP / SELL STOP reja\n"
        f"• Natija chiqqanda — qaysi orderni saqlash kerakligi\n\n"
        f"{status}\n\nBuyruqlar: /events · /plan · /vip · /status"
    )
