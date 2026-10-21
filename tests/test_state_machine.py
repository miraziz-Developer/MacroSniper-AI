import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.database import Base
from app.models.event import EconomicEvent, EventState, EventImpact
from app.engines.event_orchestrator import EventOrchestrator
from app.engines.calendar_watcher import MockCalendarProvider, CalendarWatcher, CalendarEventRaw


@pytest.fixture
async def async_test_session():
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_full_state_machine_lifecycle(async_test_session: AsyncSession):
    now = datetime.now(timezone.utc)
    mock_cpi = CalendarEventRaw(
        external_id="LIFECYCLE_CPI_2026",
        title="US Consumer Price Index (CPI) YoY",
        country="US",
        currency="USD",
        impact=EventImpact.HIGH,
        event_time=now + timedelta(hours=3),
        previous=3.1,
        forecast=3.2,
    )
    mock_watcher = CalendarWatcher(providers=[MockCalendarProvider([mock_cpi])])
    orch = EventOrchestrator(calendar_watcher=mock_watcher)

    # 1. State: SCHEDULED
    events = await orch.sync_morning_schedule(async_test_session)
    assert len(events) >= 1
    event = events[0]
    assert event.state == EventState.SCHEDULED

    # 2. State: MACRO_ANALYZED (T-3h)
    event = await orch.advance_to_t3h_macro(event.id, async_test_session)
    assert event.state == EventState.MACRO_ANALYZED
    assert event.macro_score != 0.0

    # For high-conviction test case, set aligned macro & liquidity bias
    event.macro_score = -75.0  # Bearish Gold (Hawkish USD)
    await async_test_session.commit()

    # 3. State: LIQUIDITY_MAPPED (T-1h)
    event = await orch.advance_to_t1h_liquidity(event.id, async_test_session, current_price=2650.00)
    assert event.state == EventState.LIQUIDITY_MAPPED
    assert event.liquidity_score != 0.0

    # 4. State: TRAP_DEPLOYED (T-2m / 4:58)
    signal = await orch.advance_to_t2m_pre_sniper(event.id, async_test_session, current_price=2650.00)
    assert signal is not None
    assert signal.event_id == event.id
    assert event.state == EventState.TRAP_DEPLOYED
    assert signal.limit_trap_price > 0
    assert signal.stop_break_price > 0

    # 5. State: LIVE_MONITORING & VERIFICATION (5:00:01)
    # Simulate Actual = 3.5% (High inflation -> Confirms XAUUSD Bearish Sell)
    verification = await orch.execute_instant_safety_verification(
        event_id=event.id,
        actual_value=3.5,
        session=async_test_session,
        current_price=2650.00,
    )
    assert verification.is_confirmed is True
    assert event.state == EventState.DATA_CONFIRMED


@pytest.mark.asyncio
async def test_event_time_is_returned_as_aware_utc(async_test_session: AsyncSession):
    # SQLite drops tzinfo; the Mini App countdown needs an explicit UTC offset
    tashkent = timezone(timedelta(hours=5))
    ev = EconomicEvent(title="US CPI", event_time=datetime(2026, 10, 21, 17, 30, tzinfo=tashkent))
    async_test_session.add(ev)
    await async_test_session.commit()
    async_test_session.expunge_all()

    loaded = await async_test_session.get(EconomicEvent, ev.id)
    assert loaded.event_time == datetime(2026, 10, 21, 12, 30, tzinfo=timezone.utc)
    assert loaded.event_time.isoformat().endswith("+00:00")
