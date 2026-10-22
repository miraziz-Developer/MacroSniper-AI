"""Released ('actual') values: BLS (official source, seconds after release) for NFP/CPI, FMP, else admin /actual."""

import logging
from datetime import date, datetime, timedelta
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


BLS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
# FF title -> (BLS series, how the headline is derived from the index/level)
BLS_SERIES = {
    "Non-Farm Employment Change": ("CES0000000001", "diff"),  # thousands, like FF's "228K"
    "CPI m/m": ("CUSR0000SA0", "pct"),
    "Core CPI m/m": ("CUSR0000SA0L1E", "pct"),
    "Unemployment Rate": ("LNS14000000", "level"),
    "Average Hourly Earnings m/m": ("CES0500000003", "pct"),
}


def bls_headline(title: str, data: List[Dict[str, Any]], release_day: date) -> Optional[float]:
    """Headline number for the month this release reports (the month before it), or None if not out yet."""
    _, how = BLS_SERIES[title]
    target = (release_day.year - 1, 12) if release_day.month == 1 else (release_day.year, release_day.month - 1)
    obs = sorted(
        ((int(r["year"]), int(r["period"][1:]), float(r["value"]))
         for r in data if str(r.get("period", "")).startswith("M") and r["period"] != "M13" and r.get("value") not in ("", "-")),
        reverse=True,
    )
    if not obs or obs[0][:2] != target:
        return None  # still last month's data: the new print has not landed
    current = obs[0][2]
    if how == "level":
        return current
    if len(obs) < 2:
        return None
    previous = obs[1][2]
    return round(current - previous) if how == "diff" else round((current / previous - 1) * 100, 1)


async def fetch_bls_actual(title: str, release_day: date) -> Optional[float]:
    if title not in BLS_SERIES:
        return None
    payload: Dict[str, Any] = {
        "seriesid": [BLS_SERIES[title][0]], "startyear": str(release_day.year - 1), "endyear": str(release_day.year),
    }
    if settings.BLS_API_KEY:
        payload["registrationkey"] = settings.BLS_API_KEY
    try:
        # BLS answers in 1–6 s (slower right at release); a short timeout would drop good answers
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(BLS_URL, json=payload)
        data = res.json()["Results"]["series"][0]["data"]
    except Exception as e:  # BLS is slow and flaky right at release time; the caller retries
        logger.info("BLS request failed: %s", e)
        return None
    return bls_headline(title, data, release_day)

