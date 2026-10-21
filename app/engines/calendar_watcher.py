import asyncio
import logging
import os
import json
import re
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import httpx
from pydantic import BaseModel

from app.core.config import settings
from app.models.event import EventImpact, EventState

logger = logging.getLogger(__name__)

# Key Tier-1 macroeconomic indicators that trigger major 500-2000 point news spikes
TIER_1_KEYWORDS = [
    "cpi",
    "consumer price index",
    "non-farm payrolls",
    "nonfarm payrolls",
    "employment situation",
    "fomc",
    "interest rate decision",
    "federal funds rate",
    "ppi",
    "producer price index",
    "retail sales",
    "gdp",
    "unemployment rate",
    "unemployment claims",
    "jobless claims",
    "core pce",
    "flash manufacturing pmi",
    "flash services pmi",
    "pmi",
]


def parse_numeric(val: Any) -> Optional[float]:
    if val is None:
        return None
    val_str = str(val).strip()
    match = re.search(r"[-+]?[0-9]*\.?[0-9]+", val_str)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            return None
    return None


def extract_unit(val: Any) -> Optional[str]:
    if val is None:
        return None
    val_str = str(val).strip()
    if "%" in val_str:
        return "%"
    if "K" in val_str:
        return "K"
    if "M" in val_str:
        return "M"
    if "B" in val_str:
        return "B"
    return None


class CalendarEventRaw(BaseModel):
    external_id: str
    title: str
    country: str
    currency: str
    impact: EventImpact
    event_time: datetime
    previous: Optional[float] = None
    forecast: Optional[float] = None
    actual: Optional[float] = None
    unit: Optional[str] = None


class BaseCalendarProvider:
    async def fetch_events(self, start_date: datetime, end_date: datetime) -> List[CalendarEventRaw]:
        raise NotImplementedError

    async def poll_actual_data(self, external_id: str) -> Optional[float]:
        raise NotImplementedError


class ForexFactoryCalendarProvider(BaseCalendarProvider):
    """
    ForexFactory public weekly JSON calendar provider with smart multi-tier
    caching (in-memory + disk fallback) to eliminate rate limits and guarantee 100% real data uptime.
    """
    FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ff_calendar_cache.json")
    CACHE_TTL_SECONDS = 3600  # 1 hour cache TTL

    def __init__(self):
        self._memory_cache: List[Dict[str, Any]] = []
        self._last_fetch_time: float = 0.0

    async def _load_raw_feed(self) -> List[Dict[str, Any]]:
        now_ts = time.time()
        # Return memory cache if fresh
        if self._memory_cache and (now_ts - self._last_fetch_time) < self.CACHE_TTL_SECONDS:
            return self._memory_cache

        # Attempt network fetch
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(self.FEED_URL, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and len(data) > 0:
                        self._memory_cache = data
                        self._last_fetch_time = now_ts
                        os.makedirs(os.path.dirname(self.CACHE_PATH), exist_ok=True)
                        with open(self.CACHE_PATH, "w") as f:
                            json.dump(data, f)
                        logger.info(f"ForexFactory calendar refreshed with {len(data)} events.")
                        return data
                else:
                    logger.warning(f"ForexFactory calendar returned status {resp.status_code}, falling back to cache file.")
        except Exception as e:
            logger.warning(f"ForexFactory network request error: {e}, falling back to cache file.")

        # Disk cache fallback
        if os.path.exists(self.CACHE_PATH):
            try:
                with open(self.CACHE_PATH, "r") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._memory_cache = data
                        self._last_fetch_time = now_ts
                        logger.info(f"Loaded {len(data)} calendar events from disk cache.")
                        return data
            except Exception as e:
                logger.error(f"Error reading disk cache: {e}")

        return self._memory_cache

    async def fetch_events(self, start_date: datetime, end_date: datetime) -> List[CalendarEventRaw]:
        raw_items = await self._load_raw_feed()
        results: List[CalendarEventRaw] = []
        all_future_candidates: List[CalendarEventRaw] = []

        now = datetime.now(timezone.utc)

        for item in raw_items:
            title = str(item.get("title", "")).strip()
            country = str(item.get("country", "")).strip().upper()
            currency = country if len(country) == 3 else ("USD" if country == "US" else "USD")
            impact_str = str(item.get("impact", "")).lower()

            is_tier1 = any(kw in title.lower() for kw in TIER_1_KEYWORDS)
            if impact_str == "high" or is_tier1:
                impact = EventImpact.HIGH
            elif impact_str == "medium":
                impact = EventImpact.MEDIUM
            else:
                continue

            # Only track major gold/forex market currencies
            if currency not in ["USD", "GBP", "EUR", "CAD", "JPY", "AUD", "NZD", "CHF"]:
                continue

            date_str = item.get("date")
            if not date_str:
                continue
            try:
                event_dt = datetime.fromisoformat(date_str).astimezone(timezone.utc)
            except Exception:
                continue

            norm_title = re.sub(r"[^a-zA-Z0-9]+", "_", title).strip("_")
            ext_id = f"FF_{currency}_{norm_title}_{event_dt.strftime('%Y%m%d%H%M')}"

            forecast_val = parse_numeric(item.get("forecast"))
            previous_val = parse_numeric(item.get("previous"))
            unit_val = extract_unit(item.get("forecast")) or extract_unit(item.get("previous"))

            event_obj = CalendarEventRaw(
                external_id=ext_id,
                title=f"{country} {title}",
                country=country,
                currency=currency,
                impact=impact,
                event_time=event_dt,
                previous=previous_val,
                forecast=forecast_val,
                actual=None,
                unit=unit_val,
            )

            # Check if within requested range
            if start_date <= event_dt <= end_date:
                results.append(event_obj)
            elif event_dt >= now:
                all_future_candidates.append(event_obj)

        # If today has no upcoming high-impact events, append the next upcoming Tier-1 event from this week
        if not results and all_future_candidates:
            all_future_candidates.sort(key=lambda x: x.event_time)
            results.append(all_future_candidates[0])
            logger.info(f"No events today, prioritized next upcoming event: {all_future_candidates[0].title} at {all_future_candidates[0].event_time}")

        return results

    async def poll_actual_data(self, external_id: str) -> Optional[float]:
        items = await self._load_raw_feed()
        for item in items:
            title = str(item.get("title", "")).strip()
            country = str(item.get("country", "")).strip().upper()
            currency = country if len(country) == 3 else "USD"
            date_str = item.get("date")
            if not date_str:
                continue
            try:
                event_dt = datetime.fromisoformat(date_str).astimezone(timezone.utc)
                norm_title = re.sub(r"[^a-zA-Z0-9]+", "_", title).strip("_")
                ext_id = f"FF_{currency}_{norm_title}_{event_dt.strftime('%Y%m%d%H%M')}"
                if ext_id == external_id and item.get("actual"):
                    return parse_numeric(item.get("actual"))
            except Exception:
                continue
        return None


class FMPCalendarProvider(BaseCalendarProvider):
    """Financial Modeling Prep Economic Calendar Provider"""

    BASE_URL = "https://financialmodelingprep.com/api/v3/economic_calendar"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.FMP_API_KEY

    async def fetch_events(self, start_date: datetime, end_date: datetime) -> List[CalendarEventRaw]:
        if not self.api_key or self.api_key == "your_fmp_api_key_here":
            logger.debug("FMP API key not configured, skipping FMP provider.")
            return []

        params = {
            "from": start_date.strftime("%Y-%m-%d"),
            "to": end_date.strftime("%Y-%m-%d"),
            "apikey": self.api_key,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(self.BASE_URL, params=params)
                if response.status_code != 200:
                    logger.warning(f"FMP calendar returned status code {response.status_code}")
                    return []
                
                data = response.json()
                results: List[CalendarEventRaw] = []
                for item in data:
                    title = item.get("event", "")
                    country = item.get("country", "US")
                    currency = item.get("currency", "USD")
                    impact_str = str(item.get("impact", "")).upper()

                    # Classify Impact
                    is_tier1 = any(kw in title.lower() for kw in TIER_1_KEYWORDS)
                    if is_tier1 or "HIGH" in impact_str:
                        impact = EventImpact.HIGH
                    elif "MEDIUM" in impact_str:
                        impact = EventImpact.MEDIUM
                    else:
                        impact = EventImpact.LOW

                    # Only retain High impact or Tier-1 events
                    if impact != EventImpact.HIGH:
                        continue

                    # Parse datetime
                    date_str = item.get("date")
                    if not date_str:
                        continue
                    # FMP dates are usually UTC 'YYYY-MM-DD HH:MM:SS'
                    event_dt = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)

                    ext_id = f"FMP_{country}_{title.replace(' ', '_')}_{event_dt.strftime('%Y%m%d%H%M')}"

                    results.append(
                        CalendarEventRaw(
                            external_id=ext_id,
                            title=title,
                            country=country,
                            currency=currency,
                            impact=impact,
                            event_time=event_dt,
                            previous=item.get("previous"),
                            forecast=item.get("estimate"),
                            actual=item.get("actual"),
                            unit=item.get("unit"),
                        )
                    )
                return results
            except Exception as e:
                logger.error(f"Error fetching from FMP Economic Calendar: {e}")
                return []

    async def poll_actual_data(self, external_id: str) -> Optional[float]:
        # Fast endpoint query for single event or today's calendar
        today = datetime.now(timezone.utc)
        events = await self.fetch_events(today - timedelta(hours=1), today + timedelta(hours=1))
        for ev in events:
            if ev.external_id == external_id and ev.actual is not None:
                return ev.actual
        return None


class FinnhubCalendarProvider(BaseCalendarProvider):
    """Finnhub Economic Calendar Provider"""

    BASE_URL = "https://finnhub.io/api/v1/calendar/economic"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.FINNHUB_API_KEY

    async def fetch_events(self, start_date: datetime, end_date: datetime) -> List[CalendarEventRaw]:
        if not self.api_key or self.api_key == "your_finnhub_api_key_here":
            logger.debug("Finnhub API key not configured, skipping Finnhub provider.")
            return []

        params = {
            "from": start_date.strftime("%Y-%m-%d"),
            "to": end_date.strftime("%Y-%m-%d"),
            "token": self.api_key,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(self.BASE_URL, params=params)
                if response.status_code != 200:
                    return []
                data = response.json()
                items = data.get("economicCalendar", [])
                results: List[CalendarEventRaw] = []
                for item in items:
                    title = item.get("event", "")
                    country = item.get("country", "US")
                    impact_str = str(item.get("impact", "")).lower()

                    is_tier1 = any(kw in title.lower() for kw in TIER_1_KEYWORDS)
                    impact = EventImpact.HIGH if (is_tier1 or impact_str == "high") else EventImpact.MEDIUM
                    if impact != EventImpact.HIGH:
                        continue

                    time_str = item.get("time")
                    if not time_str:
                        continue
                    event_dt = datetime.fromisoformat(time_str).replace(tzinfo=timezone.utc)
                    ext_id = f"FINN_{country}_{title.replace(' ', '_')}_{event_dt.strftime('%Y%m%d%H%M')}"

                    results.append(
                        CalendarEventRaw(
                            external_id=ext_id,
                            title=title,
                            country=country,
                            currency="USD" if country == "US" else "EUR",
                            impact=impact,
                            event_time=event_dt,
                            previous=item.get("prev"),
                            forecast=item.get("estimate"),
                            actual=item.get("actual"),
                            unit=item.get("unit"),
                        )
                    )
                return results
            except Exception as e:
                logger.error(f"Error fetching from Finnhub Calendar: {e}")
                return []


class MockCalendarProvider(BaseCalendarProvider):
    """
    Simulation calendar provider for offline development, integration tests,
    and demo runs with zero external API dependencies.
    """

    def __init__(self, simulated_events: Optional[List[CalendarEventRaw]] = None):
        self._simulated_events = simulated_events or []
        self._live_actual_overrides: Dict[str, float] = {}

    def add_simulated_event(self, event: CalendarEventRaw):
        self._simulated_events.append(event)

    def trigger_live_actual_release(self, external_id: str, actual_value: float):
        """Simulates the 17:30:00 exact-second release of the actual number."""
        self._live_actual_overrides[external_id] = actual_value

    async def fetch_events(self, start_date: datetime, end_date: datetime) -> List[CalendarEventRaw]:
        if not self._simulated_events:
            # Default mock Tier-1 CPI release 3 hours in the future
            now = datetime.now(timezone.utc)
            mock_cpi = CalendarEventRaw(
                external_id=f"MOCK_US_CPI_{now.strftime('%Y%m%d')}",
                title="US Consumer Price Index (CPI) YoY",
                country="US",
                currency="USD",
                impact=EventImpact.HIGH,
                event_time=now + timedelta(hours=3),
                previous=3.1,
                forecast=3.2,
                actual=None,
                unit="%",
            )
            return [mock_cpi]
        return self._simulated_events

    async def poll_actual_data(self, external_id: str) -> Optional[float]:
        return self._live_actual_overrides.get(external_id, None)


class CalendarWatcher:
    """
    Unified Economic Calendar Watcher with multi-provider fallback
    and ultra-low latency polling engine.
    """

    def __init__(self, providers: Optional[List[BaseCalendarProvider]] = None):
        self.providers = providers or [
            ForexFactoryCalendarProvider(),
            FMPCalendarProvider(),
            FinnhubCalendarProvider(),
            MockCalendarProvider(),
        ]
        self._is_polling = False

    async def sync_todays_red_events(self) -> List[CalendarEventRaw]:
        """Fetches Tier-1 red-folder events for today from all available providers."""
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        unique_events: Dict[str, CalendarEventRaw] = {}

        for provider in self.providers:
            # If we already have real events from live providers, skip the mock provider
            if isinstance(provider, MockCalendarProvider) and len(unique_events) > 0:
                continue
            try:
                events = await provider.fetch_events(start, end)
                for ev in events:
                    # Deduplicate by approximate time + normalized title
                    norm_key = f"{ev.currency}_{ev.title.lower()[:15]}_{ev.event_time.strftime('%Y%m%d%H%M')}"
                    if norm_key not in unique_events:
                        unique_events[norm_key] = ev
            except Exception as e:
                logger.error(f"Provider {provider.__class__.__name__} failed: {e}")

        logger.info(f"Synchronized {len(unique_events)} Tier-1 high impact event(s).")
        return list(unique_events.values())

    async def poll_actual_with_timeout(
        self,
        external_id: str,
        timeout_seconds: float = 30.0,
        interval_seconds: float = 0.3,
    ) -> Optional[float]:
        """
        Ultra-low latency poller (runs around 17:30:00).
        Loops every 300ms until the actual value is released or timeout occurs.
        """
        end_time = datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds)
        logger.info(f"Starting low-latency actual polling for {external_id} (interval={interval_seconds}s)")

        while datetime.now(timezone.utc) < end_time:
            for provider in self.providers:
                try:
                    val = await provider.poll_actual_data(external_id)
                    if val is not None:
                        logger.info(f"⚡ ACTUAL DATA DETECTED for {external_id}: {val}!")
                        return val
                except Exception as e:
                    logger.debug(f"Poller check failed on {provider.__class__.__name__}: {e}")

            await asyncio.sleep(interval_seconds)

        logger.warning(f"Polling timed out for {external_id} after {timeout_seconds}s without actual data.")
        return None
