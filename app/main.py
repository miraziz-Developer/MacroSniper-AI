import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from datetime import timedelta
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import db_alive, get_db, init_db
from app.core.security import require_admin
from app.miniapp.routes import event_dict
from app.miniapp.routes import router as miniapp_router
from app.models import Event, utcnow
from app.pipeline import orchestrator, scheduler
from app.telegram.bot import run_polling

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("macrosniper")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s (%s)", settings.APP_NAME, settings.APP_ENV)
    await init_db()
    scheduler.start()  # first calendar sync runs in the background, so the port binds immediately
    bot_task = asyncio.create_task(run_polling())
    yield
    bot_task.cancel()
    with suppress(asyncio.CancelledError):
        await bot_task
    scheduler.shutdown()


app = FastAPI(title="MacroSniper", version="2.0.0", lifespan=lifespan)
app.include_router(miniapp_router)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/miniapp")


@app.get("/health", tags=["System"])
async def health():
    db_ok = await db_alive()
    body = {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "scheduler": scheduler.scheduler.running,
        "bot": settings.bot_enabled,
        "server_time_utc": utcnow().isoformat(),
    }
    if not db_ok:
        raise HTTPException(status_code=503, detail=body)
    return body


@app.get("/api/events", tags=["Events"])
async def list_events(db: AsyncSession = Depends(get_db)):
    """Public: this week's high-impact USD releases."""
    rows = await db.execute(
        select(Event).where(Event.event_time >= utcnow() - timedelta(days=1)).order_by(Event.event_time)
    )
    return [event_dict(e) for e in rows.scalars()]


# ---------------- Admin (X-Admin-Token) ----------------


class ActualIn(BaseModel):
    value: float


@app.post("/api/admin/sync", tags=["Admin"], dependencies=[Depends(require_admin)])
async def admin_sync():
    return {"active_events": await scheduler.sync_and_schedule()}


@app.post("/api/admin/events/{event_id}/actual", tags=["Admin"], dependencies=[Depends(require_admin)])
async def admin_actual(event_id: int, body: ActualIn):
    if not await orchestrator.resolve_event(event_id, body.value, "admin api"):
        raise HTTPException(status_code=409, detail="Event not found or already resolved")
    return {"resolved": True}


@app.post("/api/admin/events/{event_id}/run/{stage}", tags=["Admin"], dependencies=[Depends(require_admin)])
async def admin_run(event_id: int, stage: Literal["context", "plan"]):
    """Manually run a stage (e.g. after downtime). Still at-most-once per event."""
    runner = orchestrator.run_context if stage == "context" else orchestrator.run_plan
    return {"ran": await runner(event_id)}
