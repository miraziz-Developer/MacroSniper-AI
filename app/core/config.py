from typing import List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    """Accepts Render/Neon style URLs (postgres://...?sslmode=require) and returns an asyncpg URL."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    if url.startswith("postgresql+asyncpg://"):
        # asyncpg rejects libpq-only params; SSL is passed via connect_args instead
        parts = urlsplit(url)
        query = [(k, v) for k, v in parse_qsl(parts.query) if k not in ("sslmode", "channel_binding")]
        url = urlunsplit(parts._replace(query=urlencode(query)))
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "MacroSniper"
    APP_ENV: str = "development"

    DATABASE_URL: str = "sqlite+aiosqlite:///./macrosniper.db"
    DATA_DIR: str = "./data_cache"

    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHANNEL_ID: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("TELEGRAM_CHANNEL_ID", "TELEGRAM_VIP_CHANNEL_ID")
    )
    TELEGRAM_ADMIN_IDS: str = ""
    MINI_APP_URL: str = "https://macrosniper-ai.onrender.com/miniapp"

    # Hourly copy of the ForexFactory feed published by .github/workflows/calendar-mirror.yml
    CALENDAR_MIRROR_URL: str = (
        "https://raw.githubusercontent.com/miraziz-Developer/MacroSniper-AI/calendar-data/ff_calendar_thisweek.json"
    )

    # Set automatically by Render; enables the keep-awake self-ping (free instances sleep after 15 min)
    RENDER_EXTERNAL_URL: Optional[str] = None

    # Admin HTTP API (X-Admin-Token); unset = admin endpoints disabled
    ADMIN_API_TOKEN: Optional[str] = None

    # Optional: automatic actual values (free tier has delays; admin /actual is the fallback)
    FMP_API_KEY: Optional[str] = None
    # Optional free key from data.bls.gov/registrationEngine: polls BLS every 1.5 s instead of 5 s
    BLS_API_KEY: Optional[str] = None

    # Subscription (Telegram Stars)
    VIP_PRICE_STARS: int = 500
    VIP_DAYS: int = 30

    # Free VIP via /promo CODE: each person once, at most PROMO_LIMIT people in total; unset = disabled
    PROMO_CODE: Optional[str] = None
    PROMO_LIMIT: int = 2
    PROMO_DAYS: int = 30

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalize_db(cls, v: str) -> str:
        return normalize_database_url(v)

    @property
    def admin_ids(self) -> List[int]:
        return [int(x) for x in (p.strip() for p in self.TELEGRAM_ADMIN_IDS.split(",")) if x.lstrip("-").isdigit()]

    @property
    def bot_enabled(self) -> bool:
        return bool(self.TELEGRAM_BOT_TOKEN)


settings = Settings()
