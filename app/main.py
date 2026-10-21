import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, Query, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict

from app.core.config import settings
from app.core.database import init_db, get_db
from app.core.redis_client import cache
from app.core.scheduler import start_scheduler, shutdown_scheduler, sync_and_schedule
from app.models.event import EconomicEvent, SniperSignal, EventState
from app.engines.event_orchestrator import orchestrator
from app.api.miniapp import router as miniapp_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("MacroSniper")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(f"Starting {settings.APP_NAME} in {settings.APP_ENV} mode...")
    await init_db()
    await cache.connect()
    # Also runs the first calendar sync in the background, so the port binds immediately
    start_scheduler()

    # Start Telegram Bot Polling concurrently if token is configured
    bot_task = None
    if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_BOT_TOKEN != "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ":
        from app.bot_main import run_bot
        bot_task = asyncio.create_task(run_bot())
        logger.info("Telegram Bot polling started concurrently in background.")

    yield

    # Shutdown
    logger.info(f"Shutting down {settings.APP_NAME}...")
    if bot_task:
        bot_task.cancel()
    shutdown_scheduler()
    await cache.close()


app = FastAPI(
    title="MacroSniper AI — Core Backend Engine",
    description="Automated AI sniper SaaS platform for high-impact macroeconomic news trading (CPI, NFP, FOMC)",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(miniapp_router)


# ==========================================
# Pydantic Schemas for API
# ==========================================
class EventResponse(BaseModel):
    id: int
    external_id: Optional[str]
    title: str
    country: str
    currency: str
    event_time: datetime
    previous: Optional[float]
    forecast: Optional[float]
    actual: Optional[float]
    state: EventState
    macro_score: float
    liquidity_score: float
    intermarket_score: float
    total_score: float
    analysis_summary: Optional[str]
    model_config = ConfigDict(from_attributes=True)


class SignalResponse(BaseModel):
    id: int
    event_id: int
    symbol: str
    bias: str
    confidence: int
    current_price_at_t2m: float
    atr_m15: float
    limit_trap_type: str
    limit_trap_price: float
    limit_sl: float
    limit_tp: float
    stop_break_type: str
    stop_break_price: float
    stop_sl: float
    stop_tp: float
    status: str
    is_kill_switch_triggered: bool
    model_config = ConfigDict(from_attributes=True)


class WebhookReleasePayload(BaseModel):
    external_id: Optional[str] = None
    event_id: Optional[int] = None
    actual: float
    current_price: Optional[float] = None


async def require_admin(x_admin_token: Optional[str] = Header(None)) -> None:
    """Guards endpoints that post to the VIP channel or touch MT5."""
    expected = settings.ADMIN_API_TOKEN
    if not expected or not secrets.compare_digest(x_admin_token or "", expected):
        raise HTTPException(status_code=403, detail="Valid X-Admin-Token header required")


# ==========================================
# API Routes
# ==========================================
@app.get("/health", tags=["System"])
async def health_check():
    redis_alive = await cache.ping()
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
        "redis_connected": redis_alive,
        "server_time_utc": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/events/today", response_model=List[EventResponse], tags=["Economic Events"])
async def get_todays_events(db: AsyncSession = Depends(get_db)):
    """Returns macroeconomic news from today (UTC) onwards."""
    start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    query = (
        select(EconomicEvent)
        .where(EconomicEvent.event_time >= start_of_day)
        .order_by(EconomicEvent.event_time.asc())
    )
    result = await db.execute(query)
    return result.scalars().all()


@app.post("/api/events/sync", tags=["Economic Events"], dependencies=[Depends(require_admin)])
async def force_sync_calendar():
    """Triggers immediate calendar synchronization."""
    count = await sync_and_schedule()
    return {"message": "Sync completed successfully", "count": count}


@app.get("/api/events/{event_id}", response_model=EventResponse, tags=["Economic Events"])
async def get_event_details(event_id: int, db: AsyncSession = Depends(get_db)):
    event = await db.get(EconomicEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@app.post("/api/events/{event_id}/trigger/{step}", tags=["Testing & Simulation"], dependencies=[Depends(require_admin)])
async def trigger_event_step(
    event_id: int,
    step: str,
    price: Optional[float] = Query(None, description="Current market price for simulation (fetches live if omitted)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually advance an event through its 5 states for instant testing:
    - step: 't3h' -> Computes F_macro score
    - step: 't1h' -> Maps MT5 liquidity zones
    - step: 't2m' -> Generates 4:58 Pre-Sniper Limit and Stop orders
    """
    if step in ("t3h", "t1h", "t2m") and not await db.get(EconomicEvent, event_id):
        raise HTTPException(status_code=404, detail="Event not found")

    if step == "t3h":
        event = await orchestrator.advance_to_t3h_macro(event_id, db)
        return {"status": "success", "state": event.state, "macro_score": event.macro_score}

    elif step == "t1h":
        event = await orchestrator.advance_to_t1h_liquidity(event_id, db, current_price=price)
        return {"status": "success", "state": event.state, "liquidity_score": event.liquidity_score}

    elif step == "t2m":
        signal = await orchestrator.advance_to_t2m_pre_sniper(event_id, db, current_price=price)
        return {
            "status": "success",
            "signal_id": signal.id,
            "bias": signal.bias,
            "limit_trap": f"{signal.limit_trap_type} @ {signal.limit_trap_price}",
            "stop_break": f"{signal.stop_break_type} @ {signal.stop_break_price}",
        }

    else:
        raise HTTPException(status_code=400, detail="Unknown step. Choose: 't3h', 't1h', or 't2m'")


@app.post("/api/webhook/actual-release", tags=["Ultra-Fast Release & Kill-Switch"], dependencies=[Depends(require_admin)])
async def webhook_actual_release(
    payload: WebhookReleasePayload,
    db: AsyncSession = Depends(get_db),
):
    """
    Ultra-low latency webhook receiver.
    Receives instantaneous actual release numbers (e.g. from Bloomberg Terminal, fast RSS, or scrapers)
    and executes the 5:00:01 Safety Verification / Kill-Switch in < 20 milliseconds!
    """
    event = None
    if payload.event_id:
        event = await db.get(EconomicEvent, payload.event_id)
    elif payload.external_id:
        q = select(EconomicEvent).where(EconomicEvent.external_id == payload.external_id)
        res = await db.execute(q)
        event = res.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="Event matching payload not found")

    result = await orchestrator.execute_instant_safety_verification(
        event_id=event.id,
        actual_value=payload.actual,
        session=db,
        current_price=payload.current_price,
    )

    return {
        "status": "executed",
        "action": result.action,
        "is_confirmed": result.is_confirmed,
        "is_kill_switch_triggered": result.is_kill_switch_triggered,
        "headline": result.headline,
        "message": result.message,
        "flip_order": result.suggested_flip_order,
    }


@app.get("/api/signals/latest", response_model=List[SignalResponse], tags=["Sniper Signals"])
async def get_latest_signals(db: AsyncSession = Depends(get_db)):
    query = select(SniperSignal).order_by(SniperSignal.id.desc()).limit(20)
    result = await db.execute(query)
    return result.scalars().all()
