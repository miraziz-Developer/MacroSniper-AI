from datetime import datetime, timedelta, timezone

import pytest

from app.billing.subscriptions import extend_vip, get_or_create_user
from app.calendar.forexfactory import CalendarItem
from app.core.db import SessionLocal
from app.market.data import LevelsInput, MacroSnapshot
from app.models import Event, EventState, Plan, utcnow
from app.pipeline import orchestrator, scheduler


@pytest.fixture
def sent(monkeypatch):
    """Captures every outgoing Telegram message instead of sending it."""
    log = {"vip": [], "channel": [], "admin": []}

    async def send_many(chat_ids, text, keyboard=None):
        ids = list(chat_ids)
        log["vip"].append((ids, text))
        return len(ids)

    async def send_channel(text, keyboard=None):
        log["channel"].append(text)
        return True

    async def send_admins(text):
        log["admin"].append(text)
        return 1

    monkeypatch.setattr(orchestrator.notifier, "send_many", send_many)
    monkeypatch.setattr(orchestrator.notifier, "send_channel", send_channel)
    monkeypatch.setattr(orchestrator.notifier, "send_admins", send_admins)
    return log


@pytest.fixture
def market(monkeypatch):
    state = {"levels": LevelsInput(4140.0, 4.0, 4145.0, 4134.0, "test"), "snap": MacroSnapshot(0.2, 1.4, 3, 24, -1.0)}

    async def levels_input():
        return state["levels"]

    async def macro_snapshot():
        return state["snap"]

    monkeypatch.setattr(orchestrator.market, "levels_input", levels_input)
    monkeypatch.setattr(orchestrator.market, "macro_snapshot", macro_snapshot)
    return state


def item(title: str, when: datetime, impact: str = "High", currency: str = "USD") -> CalendarItem:
    return CalendarItem(f"FF_{currency}_{title}_{when:%Y%m%d%H%M}", title, currency, impact, when, 0.4, 0.2, "%")


@pytest.fixture
def calendar(monkeypatch):
    items = []

    async def fetch_week():
        return items

    monkeypatch.setattr(orchestrator.forexfactory, "fetch_week", fetch_week)
    return items


async def _vip(tg_id=555):
    async with SessionLocal() as s:
        user = await get_or_create_user(s, tg_id)
        await extend_vip(s, user, 30)


async def test_sync_keeps_usd_high_plus_plannable_medium(calendar):
    soon = utcnow() + timedelta(hours=5)
    calendar += [
        item("CPI m/m", soon),
        item("FOMC Member Speaks", soon),
        item("CPI y/y", soon, currency="GBP"),
        item("Revised UoM Consumer Sentiment", soon, impact="Medium"),
        item("Unemployment Claims", soon, impact="Medium"),
        item("CPI m/m", soon, impact="Low"),
    ]
    refs = await orchestrator.sync_calendar()
    assert len(refs) == 2
    async with SessionLocal() as s:
        events = (await s.execute(Event.__table__.select())).all()
    states = sorted(e.state for e in events)
    assert len(events) == 3 and states == [EventState.SCHEDULED, EventState.SCHEDULED, EventState.SKIPPED]
    assert len(await orchestrator.sync_calendar()) == 2  # re-sync does not duplicate


async def test_full_lifecycle_sends_each_stage_once(calendar, market, sent):
    await _vip()
    calendar.append(item("CPI m/m", utcnow() + timedelta(hours=2)))
    (ref,) = await orchestrator.sync_calendar()

    assert await orchestrator.run_context(ref.id)
    assert not await orchestrator.run_context(ref.id)
    assert await orchestrator.run_plan(ref.id)
    assert not await orchestrator.run_plan(ref.id)
    assert await orchestrator.resolve_event(ref.id, 0.5, "test")
    assert not await orchestrator.resolve_event(ref.id, 0.6, "test")

    assert len(sent["vip"]) == 3 and all(ids == [555] for ids, _ in sent["vip"])
    assert "kontekst" in sent["vip"][0][1] and "SAVDO REJASI" in sent["vip"][1][1] and "NATIJA" in sent["vip"][2][1]
    assert len(sent["channel"]) == 2  # teaser + public outcome
    async with SessionLocal() as s:
        ev = await s.get(Event, ref.id)
        assert ev.state == EventState.RESOLVED and ev.outcome == "SELL" and ev.context_bias == "SELL"
        plan = (await s.execute(Plan.__table__.select())).one()
        assert plan.primary == "SELL"


async def test_plan_is_not_sent_without_market_data(calendar, market, sent):
    await _vip()
    calendar.append(item("CPI m/m", utcnow() + timedelta(minutes=30)))
    (ref,) = await orchestrator.sync_calendar()
    market["levels"] = None
    assert not await orchestrator.run_plan(ref.id)
    assert sent["vip"] == [] and len(sent["admin"]) == 1
    market["levels"] = LevelsInput(4140.0, 4.0, 4145.0, 4134.0, "test")
    assert await orchestrator.run_plan(ref.id)  # data back -> can still run once


async def test_plan_never_runs_after_release(calendar, market, sent):
    calendar.append(item("CPI m/m", utcnow() - timedelta(minutes=1)))
    (ref,) = await orchestrator.sync_calendar()
    assert not await orchestrator.run_plan(ref.id)
    assert sent["vip"] == []


async def test_poll_without_fmp_reminds_admin_once(calendar, sent):
    calendar.append(item("CPI m/m", utcnow() - timedelta(seconds=30)))
    (ref,) = await orchestrator.sync_calendar()
    await orchestrator.poll_actual(ref.id)
    await orchestrator.poll_actual(ref.id)
    assert len(sent["admin"]) == 1 and f"/actual {ref.id}" in sent["admin"][0]


def test_stage_times():
    t = datetime(2026, 10, 22, 12, 30, tzinfo=timezone.utc)
    early = scheduler.stage_times(t, EventState.SCHEDULED, t - timedelta(hours=5))
    assert early == {"context": t - timedelta(hours=3), "plan": t - timedelta(minutes=2), "poll": t + timedelta(seconds=20)}

    late_now = t - timedelta(hours=1)  # restarted inside the window: catch up context immediately
    assert scheduler.stage_times(t, EventState.SCHEDULED, late_now)["context"] == late_now

    after = scheduler.stage_times(t, EventState.PLAN_SENT, t + timedelta(minutes=1))
    assert set(after) == {"poll"}
    assert scheduler.stage_times(t, EventState.PLAN_SENT, t + timedelta(hours=1)) == {}
    assert "context" not in scheduler.stage_times(t, EventState.SCHEDULED, t - timedelta(minutes=1))
