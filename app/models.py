import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.core.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Stores UTC and always returns tz-aware UTC (SQLite silently drops tzinfo)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class EventState(str, enum.Enum):
    SCHEDULED = "SCHEDULED"  # from calendar, nothing done yet
    CONTEXT_READY = "CONTEXT_READY"  # T-2h preview (historical scenarios) sent
    PLAN_SENT = "PLAN_SENT"  # T-2m trade plan delivered
    RESOLVED = "RESOLVED"  # actual received, outcome published
    SKIPPED = "SKIPPED"  # not a numeric release we can plan (e.g. speeches)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    impact: Mapped[str] = mapped_column(String(16), default="High")
    event_time: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    forecast: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    previous: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    actual: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    state: Mapped[EventState] = mapped_column(Enum(EventState, native_enum=False), default=EventState.SCHEDULED)

    outcome: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)  # BUY / SELL / INLINE

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Plan(Base):
    """The T-2m straddle plan exactly as delivered to subscribers (single source of truth)."""

    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), unique=True)
    price: Mapped[float] = mapped_column(Float)
    atr: Mapped[float] = mapped_column(Float)
    range_high: Mapped[float] = mapped_column(Float)
    range_low: Mapped[float] = mapped_column(Float)
    buy_entry: Mapped[float] = mapped_column(Float)
    buy_sl: Mapped[float] = mapped_column(Float)
    buy_tp1: Mapped[float] = mapped_column(Float)
    buy_tp2: Mapped[float] = mapped_column(Float)
    sell_entry: Mapped[float] = mapped_column(Float)
    sell_sl: Mapped[float] = mapped_column(Float)
    sell_tp1: Mapped[float] = mapped_column(Float)
    sell_tp2: Mapped[float] = mapped_column(Float)
    price_source: Mapped[str] = mapped_column(String(32))
    result_r: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # filled by the T+2h review
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class EventStage(Base):
    """One row per (event, stage) that was executed: makes every stage at-most-once across restarts."""

    __tablename__ = "event_stages"
    __table_args__ = (UniqueConstraint("event_id", "stage", name="uq_event_stage"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    stage: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    vip_until: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    blocked_bot: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    def is_vip(self, now: Optional[datetime] = None) -> bool:
        return self.vip_until is not None and self.vip_until > (now or utcnow())


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_charge_id: Mapped[str] = mapped_column(String(128), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    stars: Mapped[int] = mapped_column(Integer)
    days: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
