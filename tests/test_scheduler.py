from datetime import datetime, timedelta, timezone

import pytest

from app.core import scheduler as sched
from app.models.event import EventState


def job_ids_for(event_id):
    return [j.id for j in sched.scheduler.get_jobs() if j.id.endswith(f"_{event_id}")]


@pytest.fixture
def t3h_calls(monkeypatch):
    calls = []

    async def fake_t3h(event_id):
        calls.append(event_id)

    monkeypatch.setattr(sched, "run_scheduled_t3h", fake_t3h)
    yield calls
    for event_id in (101, 102, 103, 104):
        for job_id in job_ids_for(event_id):
            sched.scheduler.remove_job(job_id)


@pytest.mark.asyncio
async def test_past_event_never_fires_catch_up_alert(t3h_calls):
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    await sched.schedule_event_pipeline(101, past)
    assert t3h_calls == []
    assert job_ids_for(101) == []


@pytest.mark.asyncio
async def test_non_usd_event_is_calendar_only(t3h_calls):
    soon = datetime.now(timezone.utc) + timedelta(hours=1)
    await sched.schedule_event_pipeline(102, soon, currency="GBP")
    assert t3h_calls == []
    assert job_ids_for(102) == []


@pytest.mark.asyncio
async def test_catch_up_t3h_only_when_not_yet_analyzed(t3h_calls):
    soon = datetime.now(timezone.utc) + timedelta(hours=1)
    await sched.schedule_event_pipeline(103, soon, EventState.MACRO_ANALYZED)
    assert t3h_calls == []
    await sched.schedule_event_pipeline(104, soon, EventState.SCHEDULED)
    assert t3h_calls == [104]
