from datetime import datetime, timezone
import enum
from typing import Optional
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Boolean,
    Enum as SQLEnum,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator
from app.core.database import Base


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
    SCHEDULED = "SCHEDULED"                 # Morning: retrieved from calendar
    MACRO_ANALYZED = "MACRO_ANALYZED"       # T-3h: Fundamental bias scored
    LIQUIDITY_MAPPED = "LIQUIDITY_MAPPED"   # T-1h: MT5 Order blocks & ATR mapped
    TRAP_DEPLOYED = "TRAP_DEPLOYED"         # T-2m (4:58): Limit/Stop orders generated
    LIVE_MONITORING = "LIVE_MONITORING"     # T (17:30:00): Fast Actual poller & Live Speech
    DATA_CONFIRMED = "DATA_CONFIRMED"       # T+1s: Actual aligns with forecast -> hold targets!
    SAFETY_TRIGGERED = "SAFETY_TRIGGERED"   # T+1s: Opposing surprise -> Kill-Switch cancel & flip!
    TARGET_HIT = "TARGET_HIT"               # TP reached (+500-1500 pips)
    EXPIRED = "EXPIRED"                     # Finished / Out of session
    CANCELLED = "CANCELLED"                 # Cancelled prior to execution


class EventImpact(str, enum.Enum):
    HIGH = "HIGH"         # Red folder (CPI, NFP, FOMC, PPI, Rates)
    MEDIUM = "MEDIUM"     # Orange folder
    LOW = "LOW"           # Yellow folder


class EconomicEvent(Base):
    __tablename__ = "economic_events"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String(128), unique=True, index=True, nullable=True)
    title = Column(String(255), nullable=False, index=True)
    country = Column(String(32), nullable=False, default="US")
    currency = Column(String(8), nullable=False, default="USD")
    impact = Column(SQLEnum(EventImpact), default=EventImpact.HIGH, index=True)
    
    event_time = Column(UTCDateTime, nullable=False, index=True)
    
    previous = Column(Float, nullable=True)
    forecast = Column(Float, nullable=True)
    actual = Column(Float, nullable=True)
    unit = Column(String(16), nullable=True)  # %, K, M, etc.
    
    # Deviation = Actual - Forecast
    deviation = Column(Float, nullable=True)
    surprise_direction = Column(String(16), nullable=True)  # "HAWKISH", "DOVISH", "INLINE"

    # State Machine Status
    state = Column(SQLEnum(EventState), default=EventState.SCHEDULED, nullable=False, index=True)

    # Multi-component scores (-100 to +100)
    macro_score = Column(Float, default=0.0)         # F_macro (45%)
    liquidity_score = Column(Float, default=0.0)     # T_liquidity (35%)
    intermarket_score = Column(Float, default=0.0)   # C_intermarket (20%)
    total_score = Column(Float, default=0.0)         # S_total

    # Metadata & Notes
    analysis_summary = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    signals = relationship("SniperSignal", back_populates="event", cascade="all, delete-orphan")


class SniperSignal(Base):
    __tablename__ = "sniper_signals"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("economic_events.id", ondelete="CASCADE"), nullable=False)
    
    symbol = Column(String(16), default="XAUUSD", nullable=False)
    bias = Column(String(32), nullable=False)  # "BEARISH (SELL)" or "BULLISH (BUY)"
    confidence = Column(Integer, default=50)   # 0 to 100%

    current_price_at_t2m = Column(Float, nullable=False)
    atr_m15 = Column(Float, nullable=False)

    # 1. Fake-out / Judas Swing Trap (Limit Order)
    limit_trap_type = Column(String(16), nullable=False)  # "SELL_LIMIT" / "BUY_LIMIT"
    limit_trap_price = Column(Float, nullable=False)
    limit_sl = Column(Float, nullable=False)
    limit_tp = Column(Float, nullable=False)

    # 2. Straight Breakout Order (Stop Order)
    stop_break_type = Column(String(16), nullable=False)  # "SELL_STOP" / "BUY_STOP"
    stop_break_price = Column(Float, nullable=False)
    stop_sl = Column(Float, nullable=False)
    stop_tp = Column(Float, nullable=False)

    # Safety & Kill-Switch Tracking
    is_kill_switch_triggered = Column(Boolean, default=False)
    kill_switch_reason = Column(String(255), nullable=True)

    status = Column(String(32), default="ACTIVE")  # ACTIVE, FILLED_TRAP, FILLED_BREAK, CANCELLED_KILL_SWITCH, CLOSED_TP, CLOSED_SL
    raw_payload = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    event = relationship("EconomicEvent", back_populates="signals")
