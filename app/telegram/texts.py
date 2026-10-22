"""All user-facing Telegram texts (HTML parse mode, Uzbek)."""

from datetime import datetime, timedelta, timezone
from html import escape
from typing import Optional

from app.models import Event, Plan
from app.signals.plan import Status
from app.signals import history
from app.signals.rules import classify

TASHKENT = timezone(timedelta(hours=5))
RISK_NOTE = "<i>⚠️ Bu moliyaviy maslahat emas. Bitta savdoda balansning 1–2% idan ko'p tavakkal qilmang.</i>"

SIDE_UZ = {"BUY": "🟢 BUY (oltin ko'tariladi)", "SELL": "🔴 SELL (oltin tushadi)", "INLINE": "⚪ Prognozga mos"}


def tashkent_time(dt: datetime) -> str:
    return dt.astimezone(TASHKENT).strftime("%d.%m %H:%M")


def _fmt(v: Optional[float], unit: Optional[str]) -> str:
    return "—" if v is None else f"{v:g}{unit or ''}"


def _pct(v: float) -> str:
    return f"{v * 100:.0f}%"


def event_line(ev: Event) -> str:
    return (
        f"<b>{escape(ev.title)}</b>\n"
        f"🕒 {tashkent_time(ev.event_time)} (Toshkent) · Prognoz: {_fmt(ev.forecast, ev.unit)} · Avvalgi: {_fmt(ev.previous, ev.unit)}"
    )


def scenarios(title: str) -> str:
    """'If actual > forecast gold fell X% of the time' — the honest form of 'which way, how likely'."""
    kind, stats = classify(title), history.reaction(title)
    if kind is None or stats is None:
        return ""
    up_gold = "BUY" if not kind.usd_up_when_higher else "SELL"  # gold side when actual > forecast
    down_gold = "SELL" if up_gold == "BUY" else "BUY"
    return (
        f"📊 <b>Tarix ({history.PERIOD}, {stats['n']} ta chiqish):</b>\n"
        f"• Fakt prognozdan <b>yuqori</b> → {SIDE_UZ[up_gold]}\n"
        f"• Fakt prognozdan <b>past</b> → {SIDE_UZ[down_gold]}\n"
        f"Shu yo'nalish 1 daqiqada {_pct(stats['against_1m'])}, 15 daqiqada {_pct(stats['against_15m'])} hollarda to'g'ri chiqqan; "
        f"odatiy 15 daqiqalik harakat ≈ ${stats['median_move_15m']:.2f}."
    )


def straddle_record(title: str) -> str:
    stats = history.straddle(title)
    if not stats:
        return ""
    return (
        f"📈 Shu rejaning tarixiy natijasi: {int(stats['trades'])} ta bitim, {_pct(stats['win'])} foydali, "
        f"o'rtacha {stats['exp_r']:+.2f}R har bitimga (sirpanish hisobga olingan)."
    )


def preview_message(ev: Event) -> str:
    return (
        f"🧭 <b>2 soat qoldi</b>\n\n{event_line(ev)}\n\n"
        f"Yo'nalishni oldindan hech kim aniq bilmaydi — natija faktga bog'liq.\n{scenarios(ev.title)}\n\n"
        f"{straddle_record(ev.title)}\nBUY STOP / SELL STOP rejasi yangilikdan 2 daqiqa oldin keladi."
    )


def _pips(dollars: float) -> str:
    return f"{abs(dollars) * 10:.0f} pips"  # XAUUSD: $1 = 10 pips


def _side_block(title: str, entry: float, sl: float, tp1: float, tp2: float, price: float) -> str:
    return (
        f"<b>{title}</b> <code>{entry:.2f}</code> (narxdan {entry - price:+.2f}$ = {_pips(entry - price)})\n"
        f"   SL <code>{sl:.2f}</code> ({_pips(entry - sl)}) · TP1 <code>{tp1:.2f}</code> ({_pips(tp1 - entry)})"
        f" · TP2 <code>{tp2:.2f}</code> ({_pips(tp2 - entry)})"
    )


def plan_message(ev: Event, plan: Plan) -> str:
    return (
        f"🎯 <b>XAUUSD SAVDO REJASI — 2 daqiqa qoldi</b>\n\n{event_line(ev)}\n\n"
        f"Joriy narx: <code>{plan.price:.2f}</code> ({escape(plan.price_source)}) · ATR(15m): {plan.atr:.2f}$\n"
        f"Yangilik oldi diapazoni: {plan.range_low:.2f} – {plan.range_high:.2f}\n\n"
        f"{_side_block('BUY STOP', plan.buy_entry, plan.buy_sl, plan.buy_tp1, plan.buy_tp2, plan.price)}\n"
        f"{_side_block('SELL STOP', plan.sell_entry, plan.sell_sl, plan.sell_tp1, plan.sell_tp2, plan.price)}\n\n"
        f"Ikkala orderni qo'ying; biri ochilgach ikkinchisini bekor qiling. 30 daqiqada ochilmasa — ikkalasini o'chiring.\n"
        f"TP1 da yarmini yoping va SL ni kirish narxiga o'tkazing; 2 soatdan keyin qolganini yoping.\n"
        f"Brokeringiz narxi farq qilsa, qavsdagi masofalardan foydalaning.\n\n"
        f"{straddle_record(ev.title)}\n\n{RISK_NOTE}"
    )


def outcome_message(ev: Event) -> str:
    if ev.outcome == "INLINE":
        action = "Fakt prognozga teng — kuchli impuls kutilmaydi."
    else:
        odds = history.odds(ev.title, ev.actual, ev.forecast)
        size = {0: "kichik", 1: "o'rta", 2: "katta"}.get(odds["size"]) if odds else None
        action = f"Kutilgan yo'nalish: {SIDE_UZ[ev.outcome]}." + (f" Syurpriz: {size}.\n{odds_line(odds)}" if odds else "")
    return f"⚡ <b>NATIJA CHIQDI</b>\n\n{event_line(ev)}\nFakt: <b>{_fmt(ev.actual, ev.unit)}</b>\n\n{action}"


def review_message(ev: Event, plan: Plan) -> str:
    r = plan.result_r or 0.0
    if plan.result_r == 0:
        verdict = "⚪ Orderlar ochilmadi — bekor qilindi (0R)."
    elif r > 0:
        verdict = f"✅ Foyda: <b>{r:+.2f}R</b>"
    else:
        verdict = f"❌ Zarar: <b>{r:+.2f}R</b>"
    return (
        f"🧾 <b>REJA NATIJASI</b>\n\n{escape(ev.title)} · {tashkent_time(ev.event_time)}\n{verdict}\n"
        f"<i>1R = stop-loss masofasi. Hisob 1 daqiqalik shamlar bo'yicha, sirpanish bilan.</i>"
    )


def odds_line(odds: Optional[dict]) -> str:
    """'SELL 86%' with what it is based on; empty when the release cannot be scored yet."""
    if not odds or not odds["side"]:
        return ""
    basis = {"surprise": "syurpriz kattaligi", "price": "narx harakati"}[odds["basis"]]
    return f"📊 <b>{odds['side']} {odds['p'] * 100:.0f}%</b> — 15 daqiqada shu tomonda bo'lish ehtimoli ({basis}, 2012–2025)\n"


def live_message(ev: Event, st: Status, odds: Optional[dict] = None) -> str:
    name = "BUY" if st.side == 1 else "SELL"
    head = f"📡 <b>{escape(ev.title)}</b> · jonli\n{odds_line(odds)}"
    if st.phase == "open":
        return (
            f"{head}⚡ <b>{name} STOP ochildi</b> @ <code>{st.entry:.2f}</code> — qarshi orderni bekor qiling.\n"
            f"SL <code>{st.stop:.2f}</code> ({_pips(st.entry - st.stop)}) · TP1 <code>{st.tp1:.2f}</code> "
            f"({_pips(st.tp1 - st.entry)}) · TP2 <code>{st.tp2:.2f}</code> ({_pips(st.tp2 - st.entry)})"
        )
    if st.phase == "tp1":
        return (
            f"{head}✅ <b>TP1 urildi</b> ({_pips(st.tp1 - st.entry)}). Yarmini yoping va SL ni "
            f"<code>{st.entry:.2f}</code> ga (kirish narxi) o'tkazing — bitim endi zararsiz. Keyingi maqsad TP2 "
            f"<code>{st.tp2:.2f}</code>."
        )
    if st.phase == "cancelled":
        return f"{head}⚪ 30 daqiqada hech bir order ochilmadi — ikkalasini ham bekor qiling."
    verdict = {
        "tp2": "🏆 <b>TP2 urildi</b> — bitim to'liq yopildi.",
        "sl": "❌ <b>SL urildi</b> — bitim yopildi.",
        "breakeven": "⚪ Qolgan yarmi kirish narxida yopildi (TP1 foydasi saqlandi).",
        "time": "⏱ 2 soat tugadi — qolgan pozitsiyani bozor narxida yoping.",
        "whipsaw": "⚠️ Narx bir daqiqada ikkala orderni ham urdi — ikkalasini yoping.",
    }[st.exit]
    return f"{head}{verdict}\nNatija: <b>{st.result_r:+.2f}R</b>"


def teaser_message(ev: Event) -> str:
    return f"🎯 {event_line(ev)}\n\nXAUUSD savdo rejasi VIP obunachilarga yuborildi. Obuna: botdagi /vip buyrug'i."


def welcome_message(first_name: str, is_vip: bool, vip_until: Optional[datetime]) -> str:
    status = f"💎 VIP faol: {tashkent_time(vip_until)} gacha" if is_vip and vip_until else "Holat: FREE (bepul)"
    return (
        f"Assalomu alaykum, <b>{escape(first_name)}</b>!\n\n"
        f"<b>MacroSniper</b> — AQSH makro yangiliklari paytida XAUUSD uchun 2012–2025 yillar tarixida "
        f"sinalgan savdo rejalari:\n"
        f"• 2 soat oldin — fakt yuqori/past chiqsa oltin qayerga ketgani (tarixiy %)\n"
        f"• 2 daqiqa oldin — ATR va diapazon asosida BUY STOP / SELL STOP (faqat tarixda foyda bergan yangiliklarda)\n"
        f"• Natija va 2 soatdan keyin rejaning haqiqiy hisobi (R)\n\n"
        f"{status}\n\nBuyruqlar: /events · /plan · /results · /vip · /status"
    )
