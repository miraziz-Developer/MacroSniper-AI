import logging
from datetime import timedelta
from pathlib import Path
from typing import Optional

from aiogram.types import LabeledPrice
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.subscriptions import VIP_PAYLOAD, get_or_create_user
from app.core.config import settings
from app.core.db import get_db
from app.core.security import validate_init_data
from app.market import data as market
from app.models import Event, EventState, Plan, User, utcnow
from app.pipeline import orchestrator
from app.signals import history
from app.signals.rules import classify
from app.telegram.bot import get_bot

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Mini App"])

INDEX_HTML = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")


@router.get("/miniapp", response_class=HTMLResponse)
async def miniapp_page() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML, headers={"Cache-Control": "no-cache"})


async def _viewer(session: AsyncSession, init_data: Optional[str]) -> Optional[User]:
    tg = validate_init_data(init_data or "", settings.TELEGRAM_BOT_TOKEN or "")
    if tg is None:
        return None
    return await get_or_create_user(session, tg["id"], tg.get("username"), tg.get("first_name"))


def event_dict(ev: Event) -> dict:
    return {
        "id": ev.id,
        "title": ev.title,
        "event_time": ev.event_time.isoformat(),
        "forecast": ev.forecast,
        "previous": ev.previous,
        "actual": ev.actual,
        "unit": ev.unit,
        "state": ev.state.value,
        "plannable": history.is_plannable(ev.title),
        "outcome": ev.outcome,
    }


def scenario_dict(title: str) -> Optional[dict]:
    """Historical 'if actual > forecast, gold went X' odds and the plan's backtest for this release."""
    kind, reaction = classify(title), history.reaction(title)
    if kind is None or reaction is None:
        return None
    return {
        "period": history.PERIOD,
        "higher_gold": "SELL" if kind.usd_up_when_higher else "BUY",
        **reaction,
        "straddle": history.straddle(title),
    }


def _plan_dict(plan: Plan) -> dict:
    return {
        "event_id": plan.event_id,
        "price": plan.price,
        "atr": plan.atr,
        "range": [plan.range_low, plan.range_high],
        "source": plan.price_source,
        "result_r": plan.result_r,
        "buy": {"entry": plan.buy_entry, "sl": plan.buy_sl, "tp1": plan.buy_tp1, "tp2": plan.buy_tp2},
        "sell": {"entry": plan.sell_entry, "sl": plan.sell_sl, "tp1": plan.sell_tp1, "tp2": plan.sell_tp2},
        "created_at": plan.created_at.isoformat(),
    }


@router.get("/api/app/state")
async def app_state(
    x_telegram_init_data: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Public data for everyone; the trade plan only for a verified VIP (Telegram initData)."""
    now = utcnow()
    user = await _viewer(db, x_telegram_init_data)
    is_vip = bool(user and user.is_vip(now))

    upcoming = (
        await db.execute(
            select(Event)
            .where(Event.event_time >= now - timedelta(minutes=30), Event.event_time <= now + timedelta(days=7))
            .order_by(Event.event_time)
        )
    ).scalars().all()
    results = (
        await db.execute(
            select(Event).where(Event.state == EventState.RESOLVED).order_by(Event.event_time.desc()).limit(8)
        )
    ).scalars().all()
    pending = [e for e in upcoming if e.state not in (EventState.SKIPPED, EventState.RESOLVED)]
    focus = next((e for e in pending if history.is_plannable(e.title)), pending[0] if pending else None)
    reviewed = (
        await db.execute(
            select(Plan, Event).join(Event, Plan.event_id == Event.id)
            .where(Plan.result_r.is_not(None)).order_by(Event.event_time.desc()).limit(20)
        )
    ).all()

    latest = (
        await db.execute(
            select(Plan).join(Event, Plan.event_id == Event.id)
            .where(Event.event_time >= now - timedelta(hours=6))
            .order_by(Plan.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    price, source = await market.gold_price()
    return {
        "server_time": now.isoformat(),
        "price": {"value": price, "source": source},
        "user": {
            "verified": user is not None,
            "is_vip": is_vip,
            "vip_until": user.vip_until.isoformat() if user and user.vip_until else None,
        },
        "vip": {"stars": settings.VIP_PRICE_STARS, "days": settings.VIP_DAYS},
        "focus": {**event_dict(focus), "scenario": scenario_dict(focus.title)} if focus else None,
        "plan": _plan_dict(latest) if latest and is_vip else None,
        "plan_exists": latest is not None,
        "calendar": [event_dict(e) for e in upcoming],
        "results": [event_dict(e) for e in results],
        "track_record": {
            "plans": [{"title": e.title, "event_time": e.event_time.isoformat(), "result_r": p.result_r} for p, e in reviewed],
            "total_r": round(sum(p.result_r for p, _ in reviewed), 2),
        },
    }


@router.get("/api/app/live")
async def app_live(
    x_telegram_init_data: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """VIP-only live state of the current plan (polled every ~1.5 s around the release)."""
    user = await _viewer(db, x_telegram_init_data)
    if user is None or not user.is_vip():
        raise HTTPException(status_code=403, detail="VIP only")
    now = utcnow()
    row = (
        await db.execute(
            select(Plan, Event).join(Event, Plan.event_id == Event.id)
            .where(Event.event_time >= now - timedelta(minutes=orchestrator.REVIEW_MINUTES + 5))
            .order_by(Plan.id.desc()).limit(1)
        )
    ).first()
    if row is None:
        return {"active": False}
    plan, ev = row
    if now < ev.event_time:
        return {"active": True, "phase": "pending", "release": ev.event_time.isoformat()}
    live = await market._cached(f"live:{plan.id}", 1.5, lambda: orchestrator.live_status(plan, ev.event_time))
    if live is None:
        return {"active": True, "phase": "no_data"}
    st, price = live
    return {
        "active": True, "phase": st.phase, "side": st.side, "price": price, "entry": st.entry,
        "stop": st.stop, "tp1": st.tp1, "tp2": st.tp2, "exit": st.exit, "result_r": st.result_r,
    }


@router.post("/api/app/invoice")
async def create_invoice(
    x_telegram_init_data: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _viewer(db, x_telegram_init_data)
    bot = get_bot()
    if user is None or bot is None:
        raise HTTPException(status_code=401, detail="Open the app from Telegram")
    link = await bot.create_invoice_link(
        title=f"MacroSniper VIP — {settings.VIP_DAYS} kun",
        description="XAUUSD savdo rejalari, kontekst tahlili va natija xabarlari.",
        payload=VIP_PAYLOAD,
        currency="XTR",
        prices=[LabeledPrice(label="VIP", amount=settings.VIP_PRICE_STARS)],
    )
    return {"link": link}
