import logging
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.event import EconomicEvent, EventState
from app.engines.event_orchestrator import orchestrator

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


async def schedule_event_pipeline(
    event_id: int,
    event_time: datetime,
    state: EventState = EventState.SCHEDULED,
    currency: str = "USD",
):
    """
    Schedules the 4-step timeline for a given event:
    T-3h, T-1h, T-2m, and T-10s (Fast Poller).
    """
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)

    # Signals are XAUUSD-only, so only USD releases drive the pipeline; others stay calendar-only.
    if currency != "USD":
        return
    # Already released: never fire catch-up alerts for past events (e.g. after a restart).
    if event_time <= now:
        return
    
    t_minus_3h = event_time - timedelta(hours=3)
    t_minus_1h = event_time - timedelta(hours=1)
    t_minus_2m = event_time - timedelta(minutes=2)
    t_release = event_time

    # 1. T-3 Hours: Macro Leading Scan
    if t_minus_3h > now:
        scheduler.add_job(
            run_scheduled_t3h,
            "date",
            run_date=t_minus_3h,
            args=[event_id],
            id=f"t3h_{event_id}",
            replace_existing=True,
        )
        logger.info(f"Scheduled T-3h job for event {event_id} at {t_minus_3h}")
    elif state == EventState.SCHEDULED:
        # Already within 3h and not yet analyzed: run immediately
        await run_scheduled_t3h(event_id)

    # 2. T-1 Hour: MT5 Liquidity Map
    if t_minus_1h > now:
        scheduler.add_job(
            run_scheduled_t1h,
            "date",
            run_date=t_minus_1h,
            args=[event_id],
            id=f"t1h_{event_id}",
            replace_existing=True,
        )
        logger.info(f"Scheduled T-1h job for event {event_id} at {t_minus_1h}")

    # 3. T-2 Minutes: 4:58 Pre-Sniper Signal
    if t_minus_2m > now:
        scheduler.add_job(
            run_scheduled_t2m,
            "date",
            run_date=t_minus_2m,
            args=[event_id],
            id=f"t2m_{event_id}",
            replace_existing=True,
        )
        logger.info(f"Scheduled T-2m job for event {event_id} at {t_minus_2m}")

    # 4. T-10 Seconds: Launch low-latency poller
    t_poller = event_time - timedelta(seconds=10)
    if t_poller > now:
        scheduler.add_job(
            run_scheduled_poller,
            "date",
            run_date=t_poller,
            args=[event_id],
            id=f"poller_{event_id}",
            replace_existing=True,
        )


async def run_scheduled_t3h(event_id: int):
    async with AsyncSessionLocal() as session:
        await orchestrator.advance_to_t3h_macro(event_id, session)


async def run_scheduled_t1h(event_id: int):
    async with AsyncSessionLocal() as session:
        await orchestrator.advance_to_t1h_liquidity(event_id, session)


async def run_scheduled_t2m(event_id: int):
    async with AsyncSessionLocal() as session:
        await orchestrator.advance_to_t2m_pre_sniper(event_id, session)


async def run_scheduled_poller(event_id: int):
    async with AsyncSessionLocal() as session:
        event = await session.get(EconomicEvent, event_id)
        if not event or not event.external_id:
            return

        # Start low-latency polling for actual release
        actual = await orchestrator.calendar_watcher.poll_actual_with_timeout(
            external_id=event.external_id,
            timeout_seconds=45.0,
            interval_seconds=0.25,
        )

        if actual is not None:
            # 5:00:01 instant kill-switch or confirmation check
            await orchestrator.execute_instant_safety_verification(
                event_id=event.id,
                actual_value=actual,
                session=session,
            )


async def sync_and_schedule() -> int:
    """Pulls the calendar and (re)schedules every upcoming event's timeline. Safe to repeat."""
    async with AsyncSessionLocal() as session:
        events = await orchestrator.sync_morning_schedule(session)
    for ev in events:
        await schedule_event_pipeline(ev.id, ev.event_time, ev.state, ev.currency)
    return len(events)


def start_scheduler():
    if not scheduler.running:
        # First run right away, then every 30 min so new days/weeks are picked up without a restart.
        scheduler.add_job(
            sync_and_schedule,
            "interval",
            minutes=30,
            id="calendar_sync",
            next_run_time=datetime.now(timezone.utc),
            replace_existing=True,
        )
        scheduler.start()
        logger.info("MacroSniper timeline scheduler started.")


def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("MacroSniper timeline scheduler stopped.")
