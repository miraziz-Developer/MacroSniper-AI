import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.models import EventState, utcnow
from app.pipeline import orchestrator

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")

CONTEXT_BEFORE = timedelta(hours=2)  # traders asked for 1.5–2h: 3h was too early, 1h too late
PLAN_BEFORE = timedelta(minutes=2)
POLL_AFTER = timedelta(0)  # BLS publishes at the release second
REVIEW_AFTER = timedelta(minutes=orchestrator.REVIEW_MINUTES + 5)
REVIEW_UNTIL = timedelta(days=1)


def stage_times(event_time: datetime, state: EventState, plannable: bool, now: datetime) -> Dict[str, datetime]:
    """When each remaining stage should run; overdue stages run now while they still make sense."""
    if not plannable:
        return {}
    plan_at, poll_at = event_time - PLAN_BEFORE, event_time + POLL_AFTER
    times: Dict[str, datetime] = {}
    if state == EventState.SCHEDULED and now < plan_at:
        times["context"] = max(event_time - CONTEXT_BEFORE, now)
    if state in (EventState.SCHEDULED, EventState.CONTEXT_READY) and now < event_time:
        times["plan"] = max(plan_at, now)
    if state != EventState.RESOLVED and now < event_time + orchestrator.POLL_WINDOW:
        times["poll"] = max(poll_at, now)
    if now < event_time + timedelta(minutes=orchestrator.REVIEW_MINUTES):
        times["live"] = max(event_time - timedelta(seconds=30), now)
    if now < event_time + REVIEW_UNTIL:  # retried by each re-sync until candles are available
        times["review"] = max(event_time + REVIEW_AFTER, now)
    return times


_JOBS = {
    "context": orchestrator.run_context,
    "plan": orchestrator.run_plan,
    "poll": orchestrator.poll_actual,
    "review": orchestrator.run_review,
    "live": orchestrator.run_live,
}


def schedule_event(ref: orchestrator.EventRef, now: Optional[datetime] = None) -> None:
    for stage, run_at in stage_times(ref.event_time, ref.state, ref.plannable, now or utcnow()).items():
        # Re-adding is safe: same id replaces the job and stages are idempotent in the DB
        scheduler.add_job(
            _JOBS[stage],
            "date",
            run_date=run_at,
            args=[ref.id],
            id=f"{stage}_{ref.id}",
            replace_existing=True,
            misfire_grace_time=90,
        )


async def sync_and_schedule() -> int:
    refs = await orchestrator.sync_calendar()
    for ref in refs:
        schedule_event(ref)
    logger.info("Calendar synced: %d active event(s)", len(refs))
    return len(refs)


async def keep_awake() -> None:
    # Inbound request through Render's public URL resets the free-tier idle timer
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.get(f"{settings.RENDER_EXTERNAL_URL.rstrip('/')}/health")
    except Exception as e:
        logger.warning("Keep-awake ping failed: %s", e)


def start() -> None:
    if scheduler.running:
        return
    if settings.RENDER_EXTERNAL_URL:
        scheduler.add_job(keep_awake, "interval", minutes=10, id="keep_awake", replace_existing=True)
    # First sync right away, then every 10 min: retries soon after a ForexFactory 429 on a fresh instance
    scheduler.add_job(
        sync_and_schedule, "interval", minutes=10, id="calendar_sync", next_run_time=utcnow(), replace_existing=True
    )
    scheduler.start()


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
