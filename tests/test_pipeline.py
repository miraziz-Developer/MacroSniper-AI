from datetime import datetime, timedelta, timezone

import pytest

from app.billing.subscriptions import extend_vip, get_or_create_user
from app.calendar.forexfactory import CalendarItem
from app.core.db import SessionLocal
from app.market.data import LevelsInput
from app.market.indicators import Candle
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


NFP = "Non-Farm Employment Change"  # plannable (positive backtest); Unemployment Claims is not


@pytest.fixture
def market(monkeypatch):
    # plan from these levels: BUY STOP 4143.70 / SELL STOP 4136.30, 1R = $8
    rally = [Candle(i, 4140, 4144 if i == 0 else 4170, 4140, 4144) for i in range(130)]
    state = {"levels": LevelsInput(4140.0, 4.0, 4145.0, 4134.0, "test"), "minutes": rally}

    async def levels_input():
        return state["levels"]

    async def minute_candles(source, start, minutes):
        return state["minutes"]

    monkeypatch.setattr(orchestrator.market, "levels_input", levels_input)
    monkeypatch.setattr(orchestrator.market, "minute_candles", minute_candles)
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
    calendar.append(item(NFP, utcnow() + timedelta(hours=2)))
    (ref,) = await orchestrator.sync_calendar()
    assert ref.plannable

    assert await orchestrator.run_context(ref.id)
    assert not await orchestrator.run_context(ref.id)
    assert await orchestrator.run_plan(ref.id)
    assert not await orchestrator.run_plan(ref.id)
    assert await orchestrator.resolve_event(ref.id, 0.5, "test")
    assert not await orchestrator.resolve_event(ref.id, 0.6, "test")
    assert await orchestrator.run_review(ref.id)
    assert not await orchestrator.run_review(ref.id)

    texts_sent = [text for _, text in sent["vip"]]
    assert len(texts_sent) == 4 and all(ids == [555] for ids, _ in sent["vip"])
    assert "2 soat qoldi" in texts_sent[0] and "Tarix" in texts_sent[0]
    assert "SAVDO REJASI" in texts_sent[1] and "pips" in texts_sent[1] and "NATIJA CHIQDI" in texts_sent[2] and "REJA NATIJASI" in texts_sent[3]
    assert len(sent["channel"]) == 3  # teaser + public outcome + public review
    async with SessionLocal() as s:
        ev = await s.get(Event, ref.id)
        assert ev.state == EventState.RESOLVED and ev.outcome == "SELL"
        plan = (await s.execute(Plan.__table__.select())).one()
        assert plan.result_r > 2  # TP1 and TP2 both hit in the rally


async def test_unplannable_release_gets_no_preview_or_plan(calendar, market, sent):
    await _vip()
    calendar.append(item("Unemployment Claims", utcnow() + timedelta(hours=2)))
    (ref,) = await orchestrator.sync_calendar()
    assert not ref.plannable
    assert not await orchestrator.run_context(ref.id) and not await orchestrator.run_plan(ref.id)
    assert sent["vip"] == []


async def test_review_waits_for_enough_candles(calendar, market, sent):
    await _vip()
    calendar.append(item(NFP, utcnow() + timedelta(minutes=30)))
    (ref,) = await orchestrator.sync_calendar()
    assert await orchestrator.run_plan(ref.id)
    market["minutes"] = [Candle(i, 4140, 4140.2, 4139.8, 4140) for i in range(10)]
    assert not await orchestrator.run_review(ref.id)  # undecided: retried by the next sync
    market["minutes"] = [Candle(i, 4140, 4140.2, 4139.8, 4140) for i in range(40)]
    assert await orchestrator.run_review(ref.id)
    async with SessionLocal() as s:
        assert (await s.execute(Plan.__table__.select())).one().result_r == 0.0  # never triggered


async def test_plan_is_not_sent_without_market_data(calendar, market, sent):
    await _vip()
    calendar.append(item(NFP, utcnow() + timedelta(minutes=30)))
    (ref,) = await orchestrator.sync_calendar()
    market["levels"] = None
    assert not await orchestrator.run_plan(ref.id)
    assert sent["vip"] == [] and len(sent["admin"]) == 1
    market["levels"] = LevelsInput(4140.0, 4.0, 4145.0, 4134.0, "test")
    assert await orchestrator.run_plan(ref.id)  # data back -> can still run once


async def test_plan_never_runs_after_release(calendar, market, sent):
    calendar.append(item(NFP, utcnow() - timedelta(minutes=1)))
    (ref,) = await orchestrator.sync_calendar()
    assert not await orchestrator.run_plan(ref.id)
    assert sent["vip"] == []


async def test_poll_without_fmp_reminds_admin_once(calendar, sent):
    calendar.append(item(NFP, utcnow() - timedelta(seconds=30)))
    (ref,) = await orchestrator.sync_calendar()
    await orchestrator.poll_actual(ref.id)
    await orchestrator.poll_actual(ref.id)
    assert len(sent["admin"]) == 1 and f"/actual {ref.id}" in sent["admin"][0]


def test_stage_times():
    t = datetime(2026, 10, 22, 12, 30, tzinfo=timezone.utc)
    review_at = t + timedelta(minutes=125)
    early = scheduler.stage_times(t, EventState.SCHEDULED, True, t - timedelta(hours=5))
    assert early == {
        "context": t - timedelta(hours=2),
        "plan": t - timedelta(minutes=2),
        "poll": t + timedelta(seconds=20),
        "review": review_at,
    }
    assert scheduler.stage_times(t, EventState.SCHEDULED, False, t - timedelta(hours=5)) == {}

    late_now = t - timedelta(hours=1)  # restarted inside the window: catch up the preview immediately
    assert scheduler.stage_times(t, EventState.SCHEDULED, True, late_now)["context"] == late_now

    after = scheduler.stage_times(t, EventState.PLAN_SENT, True, t + timedelta(minutes=1))
    assert set(after) == {"poll", "review"}
    resolved = scheduler.stage_times(t, EventState.RESOLVED, True, t + timedelta(hours=3))
    assert resolved == {"review": t + timedelta(hours=3)}  # overdue review runs now
    assert scheduler.stage_times(t, EventState.RESOLVED, True, t + timedelta(days=2)) == {}


async def test_keep_awake_pings_public_health(monkeypatch):
    calls = []

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url):
            calls.append(url)

    monkeypatch.setattr(scheduler.settings, "RENDER_EXTERNAL_URL", "https://x.onrender.com/")
    monkeypatch.setattr(scheduler.httpx, "AsyncClient", FakeClient)
    await scheduler.keep_awake()
    assert calls == ["https://x.onrender.com/health"]
