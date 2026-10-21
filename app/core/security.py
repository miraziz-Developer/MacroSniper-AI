import hashlib
import hmac
import json
import secrets
import time
from typing import Optional
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException

from app.core.config import settings

INIT_DATA_MAX_AGE_SECONDS = 24 * 3600


def validate_init_data(init_data: str, bot_token: str, max_age: int = INIT_DATA_MAX_AGE_SECONDS) -> Optional[dict]:
    """Verifies Telegram Mini App initData (HMAC-SHA256) and returns the Telegram user dict, else None."""
    if not init_data or not bot_token:
        return None
    try:
        fields = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None
    received_hash = fields.pop("hash", "")
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return None
    try:
        if time.time() - int(fields.get("auth_date", "0")) > max_age:
            return None
        user = json.loads(fields.get("user", "null"))
    except (ValueError, TypeError):
        return None
    return user if isinstance(user, dict) and isinstance(user.get("id"), int) else None


async def require_admin(x_admin_token: Optional[str] = Header(None)) -> None:
    expected = settings.ADMIN_API_TOKEN
    if not expected or not secrets.compare_digest(x_admin_token or "", expected):
        raise HTTPException(status_code=403, detail="Valid X-Admin-Token header required")
