"""Event lifecycle: SCHEDULED -> CONTEXT_READY -> PLAN_SENT -> RESOLVED (+ plan review). Each stage runs at most once."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from html import escape
from typing import List

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.subscriptions import active_vip_chat_ids
from app.calendar import actuals, forexfactory
from app.core.config import settings
from app.core.db import SessionLocal
from app.market import data as market
from app.models import Event, EventStage, EventState, Plan, utcnow
from app.signals import history
from app.signals.outcome import resolve
from app.signals.plan import Side, TradePlan, build_plan, simulate
from app.signals.rules import classify
from app.telegram import notifier, texts

logger = logging.getLogger(__name__)

POLL_WINDOW = timedelta(minutes=15)
POLL_INTERVAL_SECONDS = 30
REVIEW_MINUTES = 120  # plan is judged on the first 2 hours after release (same as the backtest)
REVIEW_SLIPPAGE = 0.5
_polled: set = set()  # per-process guard: the periodic re-sync must not start a second poll loop


@dataclass(frozen=True)
class EventRef:
    id: int
    event_time: datetime
    state: EventState
    plannable: bool


def app_keyboard(private: bool = True) -> InlineKeyboardMarkup:
    # web_app buttons are only allowed in private chats; channels get a plain link
    button = (
        InlineKeyboardButton(text="📱 Mini App", web_app=WebAppInfo(url=settings.MINI_APP_URL))
        if private
        else InlineKeyboardButton(text="📱 Mini App", url=settings.MINI_APP_URL)
    )
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


async def _claim_stage(session: AsyncSession, event_id: int, stage: str) -> bool:
    session.add(EventStage(event_id=event_id, stage=stage))
    try:
        await session.commit()
        return True
    except IntegrityError:
        await session.rollback()
        return False


async def sync_calendar() -> List[EventRef]:
    """Upserts this week's USD releases (all High + Medium ones we can classify); returns the last day's and upcoming."""
    items = await forexfactory.fetch_week()
    async with SessionLocal() as session:
        for it in items:
            kind = classify(it.title)
            # ForexFactory rates e.g. Unemployment Claims "Medium", yet it reliably moves gold
            if it.currency != "USD" or not (it.impact == "High" or (it.impact == "Medium" and kind)):
                continue
            ev = (await session.execute(select(Event).where(Event.external_id == it.external_id))).scalar_one_or_none()
            if ev is None:
                session.add(
                    Event(
                        external_id=it.external_id,
                        title=it.title,
                        currency=it.currency,
                        impact=it.impact,
                        event_time=it.event_time,
                        forecast=it.forecast,
                        previous=it.previous,
                        unit=it.unit,
                        state=EventState.SCHEDULED if kind else EventState.SKIPPED,
                    )
                )
            elif ev.state in (EventState.SCHEDULED, EventState.CONTEXT_READY):
                ev.forecast, ev.previous, ev.unit = it.forecast, it.previous, it.unit  # revisions
        await session.commit()

        rows = await session.execute(
            select(Event.id, Event.event_time, Event.state, Event.title).where(
                Event.state != EventState.SKIPPED, Event.event_time > utcnow() - timedelta(days=1)
            )
        )
        return [EventRef(i, t, st, history.is_plannable(title)) for i, t, st, title in rows]


async def run_context(event_id: int) -> bool:
    """T-3h preview for plannable releases: historical scenarios, no direction claims."""
    async with SessionLocal() as session:
        ev = await session.get(Event, event_id)
        if ev is None or ev.state != EventState.SCHEDULED or not history.is_plannable(ev.title):
            return False
        if not await _claim_stage(session, event_id, "context"):
            return False
        ev.state = EventState.CONTEXT_READY
        await session.commit()
        vips = await active_vip_chat_ids(session)
    await notifier.send_many(vips, texts.preview_message(ev), app_keyboard())
    return True


async def run_plan(event_id: int) -> bool:
    async with SessionLocal() as session:
        ev = await session.get(Event, event_id)
        if ev is None or ev.state not in (EventState.SCHEDULED, EventState.CONTEXT_READY):
            return False
        if ev.event_time <= utcnow() or not history.is_plannable(ev.title):
            return False
        levels = await market.levels_input()
        if levels is None:
            # Never invent prices: tell admins and send nothing to subscribers
            await notifier.send_admins(f"⚠️ {escape(ev.title)}: narx ma'lumoti olinmadi, reja yuborilmadi.")
            return False
        if not await _claim_stage(session, event_id, "plan"):
            return False
        tp = build_plan(levels.price, levels.atr, levels.range_high, levels.range_low)
        plan = Plan(
            event_id=ev.id,
            price=tp.price,
            atr=tp.atr,
            range_high=tp.range_high,
            range_low=tp.range_low,
            buy_entry=tp.buy.entry,
            buy_sl=tp.buy.sl,
            buy_tp1=tp.buy.tp1,
            buy_tp2=tp.buy.tp2,
            sell_entry=tp.sell.entry,
            sell_sl=tp.sell.sl,
            sell_tp1=tp.sell.tp1,
            sell_tp2=tp.sell.tp2,
            price_source=levels.source,
        )
        session.add(plan)
        ev.state = EventState.PLAN_SENT
        await session.commit()
        vips = await active_vip_chat_ids(session)
    await notifier.send_many(vips, texts.plan_message(ev, plan), app_keyboard())
    await notifier.send_channel(texts.teaser_message(ev), app_keyboard(private=False))
    logger.info("Plan sent for event %s to %d VIPs", event_id, len(vips))
    return True


async def resolve_event(event_id: int, actual: float, source: str) -> bool:
    async with SessionLocal() as session:
        ev = await session.get(Event, event_id)
        if ev is None or ev.state in (EventState.RESOLVED, EventState.SKIPPED):
            return False
        kind = classify(ev.title)
        if kind is None or not await _claim_stage(session, event_id, "outcome"):
            return False
        had_plan = ev.state == EventState.PLAN_SENT
        ev.actual = actual
        ev.outcome = resolve(kind, actual, ev.forecast, ev.previous)
        ev.state = EventState.RESOLVED
        await session.commit()
        vips = await active_vip_chat_ids(session) if had_plan else []
    message = texts.outcome_message(ev)
    await notifier.send_many(vips, message, app_keyboard())
    await notifier.send_channel(message, app_keyboard(private=False))
    await notifier.send_admins(f"✅ {escape(ev.title)}: fakt {actual:g} ({source}) → {ev.outcome}")
    return True


async def poll_actual(event_id: int) -> None:
    if event_id in _polled:
        return
    _polled.add(event_id)
    async with SessionLocal() as session:
        ev = await session.get(Event, event_id)
        if ev is None or ev.state in (EventState.RESOLVED, EventState.SKIPPED) or not history.is_plannable(ev.title):
            return
        title, event_time, previous = ev.title, ev.event_time, ev.previous

    reminder = f"✍️ {escape(title)} chiqdi. Faktni kiriting: <code>/actual {event_id} QIYMAT</code>"
    if not settings.FMP_API_KEY:
        await notifier.send_admins(reminder)
        return
    deadline = event_time + POLL_WINDOW
    while utcnow() < deadline:
        value = await actuals.fetch_fmp_actual(title, event_time, previous)
        if value is not None:
            await resolve_event(event_id, value, "FMP")
            return
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    await notifier.send_admins(reminder)


def to_trade_plan(plan: Plan) -> TradePlan:
    return TradePlan(
        price=plan.price,
        atr=plan.atr,
        range_high=plan.range_high,
        range_low=plan.range_low,
        buy=Side(plan.buy_entry, plan.buy_sl, plan.buy_tp1, plan.buy_tp2),
        sell=Side(plan.sell_entry, plan.sell_sl, plan.sell_tp1, plan.sell_tp2),
    )


async def run_review(event_id: int) -> bool:
    """T+2h: score the delivered plan on real 1-minute candles with the backtest's own rules."""
    async with SessionLocal() as session:
        plan = (await session.execute(select(Plan).where(Plan.event_id == event_id))).scalar_one_or_none()
        ev = await session.get(Event, event_id)
        if plan is None or ev is None or plan.result_r is not None:
            return False
        candles = await market.minute_candles(plan.price_source, ev.event_time, REVIEW_MINUTES)
        result = simulate(to_trade_plan(plan), [(c.open, c.high, c.low, c.close) for c in candles or []], REVIEW_SLIPPAGE)
        if result is None:
            logger.warning("Review of event %s: not enough candles yet", event_id)
            return False
        if not await _claim_stage(session, event_id, "review"):
            return False
        plan.result_r = result
        await session.commit()
        vips = await active_vip_chat_ids(session)
    message = texts.review_message(ev, plan)
    await notifier.send_many(vips, message, app_keyboard())
    await notifier.send_channel(message, app_keyboard(private=False))
    return True
