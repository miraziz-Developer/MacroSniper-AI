"""ForexFactory weekly calendar (free JSON feed) with memory + disk cache — the feed rate-limits hard (429)."""

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CACHE_TTL_SECONDS = 3600
_NUM = re.compile(r"[-+]?\d*\.?\d+")

_memory: List[Dict[str, Any]] = []
_fetched_at = 0.0


@dataclass(frozen=True)
class CalendarItem:
    external_id: str
    title: str
    currency: str
    impact: str  # High / Medium / Low / Holiday
    event_time: datetime  # UTC
    forecast: Optional[float]
    previous: Optional[float]
    unit: Optional[str]


def parse_number(raw: Any) -> Optional[float]:
    """'225K' -> 225.0, '-0.3%' -> -0.3, '' -> None. Units are kept separately."""
    match = _NUM.search(str(raw or ""))
    return float(match.group(0)) if match else None


def parse_unit(raw: Any) -> Optional[str]:
    text = str(raw or "")
    for unit in ("%", "K", "M", "B", "T"):
        if unit in text:
            return unit
    return None


def parse_items(raw_items: List[Dict[str, Any]]) -> List[CalendarItem]:
    items: List[CalendarItem] = []
    for raw in raw_items:
        title = str(raw.get("title", "")).strip()
        currency = str(raw.get("country", "")).strip().upper()
        try:
            event_time = datetime.fromisoformat(str(raw.get("date"))).astimezone(timezone.utc)
        except ValueError:
            continue
        if not title or len(currency) != 3 or currency == "ALL":  # "All" = multi-currency meetings
            continue
        slug = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_")
        items.append(
            CalendarItem(
                external_id=f"FF_{currency}_{slug}_{event_time:%Y%m%d%H%M}",
                title=title,
                currency=currency,
                impact=str(raw.get("impact", "")),
                event_time=event_time,
                forecast=parse_number(raw.get("forecast")),
                previous=parse_number(raw.get("previous")),
                unit=parse_unit(raw.get("forecast")) or parse_unit(raw.get("previous")),
            )
        )
    return items


def _cache_path() -> str:
    return os.path.join(settings.DATA_DIR, "ff_calendar.json")


async def _load_raw() -> List[Dict[str, Any]]:
    global _memory, _fetched_at
    if _memory and time.time() - _fetched_at < CACHE_TTL_SECONDS:
        return _memory
    # Cloudflare in front of ForexFactory often blocks cloud IPs; the GitHub mirror is the fallback
    for url in (FEED_URL, settings.CALENDAR_MIRROR_URL):
        try:
            async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
                res = await client.get(url)
            data = res.json() if res.status_code == 200 else None
            if isinstance(data, list) and data:
                _memory, _fetched_at = data, time.time()
                os.makedirs(settings.DATA_DIR, exist_ok=True)
                with open(_cache_path(), "w") as f:
                    json.dump(_memory, f)
                return _memory
            logger.warning("Calendar source %s returned HTTP %s", url, res.status_code)
        except Exception as e:
            logger.warning("Calendar source %s failed: %s", url, e)

    if not _memory and os.path.exists(_cache_path()):
        try:
            with open(_cache_path()) as f:
                _memory = json.load(f)
        except (OSError, ValueError):
            logger.exception("Calendar disk cache unreadable")
    # Back off for 10 min before retrying the network after a failure
    _fetched_at = time.time() - CACHE_TTL_SECONDS + 600
    return _memory


async def fetch_week() -> List[CalendarItem]:
    return parse_items(await _load_raw())
