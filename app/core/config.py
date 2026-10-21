from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    APP_NAME: str = "MacroSniper AI"
    APP_ENV: str = "development"
    APP_PORT: int = Field(default=8000, validation_alias="PORT")
    SECRET_KEY: str = "secret-sniper-key"

    # Database & Cache
    DATABASE_URL: str = "sqlite+aiosqlite:///./macrosniper.db"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Economic Data API Keys
    FMP_API_KEY: Optional[str] = None
    FINNHUB_API_KEY: Optional[str] = None
    ALPHA_VANTAGE_API_KEY: Optional[str] = None

    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_VIP_CHANNEL_ID: Optional[str] = None
    TELEGRAM_FREE_CHANNEL_ID: Optional[str] = None
    TELEGRAM_ADMIN_IDS: str = ""
    MINI_APP_URL: str = "https://macrosniper-ai.onrender.com/miniapp"

    @property
    def admin_id_list(self) -> List[int]:
        if not self.TELEGRAM_ADMIN_IDS:
            return []
        return [int(x.strip()) for x in self.TELEGRAM_ADMIN_IDS.split(",") if x.strip().isdigit()]

    # Audio AI
    DEEPGRAM_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None

    # MT5 Broker Settings
    MT5_ENABLED: bool = False
    MT5_SERVER: Optional[str] = None
    MT5_LOGIN: Optional[int] = None
    MT5_PASSWORD: Optional[str] = None
    MT5_PATH: Optional[str] = None

    # Trading & Risk Rules
    DEFAULT_SPREAD_BUFFER_GOLD: float = 1.80  # XAUUSD news spread buffer in points ($)
    DEFAULT_ATR_PERIOD: int = 14
    HIGH_CONVICTION_THRESHOLD: float = 65.0   # |S_total| >= 65 -> Limit Trap + Stop Breakout
    MEDIUM_CONVICTION_THRESHOLD: float = 40.0 # 40 <= |S_total| < 65 -> Wide Limit Trap only
    KILL_SWITCH_AUTO_EXECUTE: bool = True     # 5:00:01 emergency cancel & flip if shock occurs


settings = Settings()
