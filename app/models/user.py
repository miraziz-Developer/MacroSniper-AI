from datetime import datetime, timezone
import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum as SQLEnum, BigInteger
from app.core.database import Base


class SubscriptionTier(str, enum.Enum):
    FREE = "FREE"
    VIP_PRO = "VIP_PRO"             # Full 4:58 signals, dark cards, instant kill-switch
    ENTERPRISE = "ENTERPRISE"       # Auto-Copier MT5 bridge with < 200ms latency


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String(64), nullable=True)
    first_name = Column(String(128), nullable=True)
    
    tier = Column(SQLEnum(SubscriptionTier), default=SubscriptionTier.FREE, nullable=False)
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # MT5 Copier Configuration
    mt5_account = Column(String(32), nullable=True)
    mt5_server = Column(String(64), nullable=True)
    auto_trade_enabled = Column(Boolean, default=False)
    lot_size = Column(String(16), default="0.50")

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
