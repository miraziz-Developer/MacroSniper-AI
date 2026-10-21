"""Released ('actual') values. Automatic only with FMP_API_KEY; otherwise admins enter them with /actual."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.signals.rules import classify

logger = logging.getLogger(__name__)

FMP_URL = "https://financialmodelingprep.com/stable/economic-calendar"


def _num(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def match_actual(
    title: str,
    event_time: datetime,
    previous: Optional[float],
    items: List[Dict[str, Any]],
) -> Optional[float]:
    """Finds the same US release in FMP data and returns its actual in our (ForexFactory) units."""
    kind = classify(title)
    if kind is None:
        return None
    for item in items:
        if str(item.get("country", "")).upper() not in ("US", "USA"):
            continue
        name = str(item.get("event", ""))
        if classify(name) != kind:
            continue
        try:
            fmp_time = datetime.fromisoformat(str(item.get("date"))).replace(tzinfo=event_time.tzinfo)
        except ValueError:
            continue
        if abs(fmp_time - event_time) > timedelta(minutes=5):
            continue
        actual = _num(item.get("actual"))
        if actual is None:
            return None
        # Same series, different scale (e.g. 225000 vs 225K): rescale via the shared 'previous'
        fmp_prev = _num(item.get("previous"))
        if previous and fmp_prev and abs(previous / fmp_prev - 1) > 0.5:
            actual *= previous / fmp_prev
        return round(actual, 4)
    return None


async def fetch_fmp_actual(title: str, event_time: datetime, previous: Optional[float]) -> Optional[float]:
    if not settings.FMP_API_KEY:
        return None
    params = {"from": f"{event_time:%Y-%m-%d}", "to": f"{event_time:%Y-%m-%d}", "apikey": settings.FMP_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(FMP_URL, params=params)
        if res.status_code != 200:
            logger.warning("FMP calendar HTTP %s", res.status_code)
            return None
        data = res.json()
    except Exception as e:
        logger.warning("FMP calendar request failed: %s", e)
        return None
    return match_actual(title, event_time, previous, data if isinstance(data, list) else [])
