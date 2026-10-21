import asyncio
import logging
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
    "core pce",
]


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
