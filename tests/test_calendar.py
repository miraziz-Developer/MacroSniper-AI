import pytest
from datetime import datetime, timezone, timedelta
from app.engines.calendar_watcher import MockCalendarProvider, CalendarWatcher, CalendarEventRaw
from app.models.event import EventImpact


@pytest.mark.asyncio
async def test_mock_calendar_provider_fetch():
    now = datetime.now(timezone.utc)
    mock_ev = CalendarEventRaw(
        external_id="TEST_CPI_001",
        title="US Core CPI MoM",
        country="US",
        currency="USD",
        impact=EventImpact.HIGH,
        event_time=now + timedelta(hours=2),
        previous=0.3,
        forecast=0.3,
    )
    provider = MockCalendarProvider([mock_ev])
    events = await provider.fetch_events(now, now + timedelta(days=1))

    assert len(events) == 1
    assert events[0].title == "US Core CPI MoM"


@pytest.mark.asyncio
async def test_calendar_watcher_fast_poll():
    mock_provider = MockCalendarProvider()
    watcher = CalendarWatcher(providers=[mock_provider])

    # Simulate actual release triggered after a short delay
    mock_provider.trigger_live_actual_release("MOCK_CPI_EVENT", 3.5)

    actual = await watcher.poll_actual_with_timeout(
        external_id="MOCK_CPI_EVENT",
        timeout_seconds=2.0,
        interval_seconds=0.1,
    )

    assert actual == 3.5
