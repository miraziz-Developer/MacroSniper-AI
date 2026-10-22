"""Free gold market data: PAXG (tracks spot) on Binance, then Kraken (works from US clouds), then COMEX futures."""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import httpx

from app.market.indicators import Candle, atr, recent_range

logger = logging.getLogger(__name__)

BINANCE = "https://api.binance.com/api/v3"
KRAKEN = "https://api.kraken.com/0/public"
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart"
HEADERS = {"User-Agent": "Mozilla/5.0 (MacroSniper)"}
PAXG, KRAKEN_PAXG, COMEX = "Binance PAXG", "Kraken PAXG", "COMEX GC=F"  # source names, stored with each plan
TIMEOUT = httpx.Timeout(6.0)

_cache: Dict[str, Tuple[float, Any]] = {}


async def _cached(key: str, ttl: float, loader: Callable[[], Awaitable[Any]]) -> Any:
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    value = await loader()
    if value is not None:  # never cache failures
        _cache[key] = (time.time(), value)
    return value


async def _get_json(url: str, params: Optional[dict] = None) -> Optional[Any]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS) as client:
            res = await client.get(url, params=params)
            res.raise_for_status()
            return res.json()
    except Exception as e:
        logger.warning("Market request failed %s: %s", url, e)
        return None


async def _binance_candles(interval: str, limit: int, start_ms: Optional[int] = None) -> Optional[List[Candle]]:
    params = {"symbol": "PAXGUSDT", "interval": interval, "limit": limit}
    if start_ms is not None:
        params["startTime"] = start_ms
    data = await _get_json(f"{BINANCE}/klines", params)
    if not isinstance(data, list) or not data:
        return None
    try:
        return [Candle(int(k[0]) // 1000, float(k[1]), float(k[2]), float(k[3]), float(k[4])) for k in data]
    except (IndexError, TypeError, ValueError):
        return None


async def _kraken_candles(interval_min: int, since: Optional[int] = None) -> Optional[List[Candle]]:
    # shortcut: Kraken returns at most the last 720 candles (12h at 1m); review runs ~2h after release
    params = {"pair": "PAXGUSD", "interval": interval_min}
    if since is not None:
        params["since"] = since
    data = await _get_json(f"{KRAKEN}/OHLC", params)
    try:
        rows = next(v for k, v in data["result"].items() if k != "last")
        return [Candle(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])) for r in rows] or None
    except (KeyError, StopIteration, TypeError, ValueError, IndexError):
        return None


async def _yahoo_candles(symbol: str, interval: str, rng: str) -> Optional[List[Candle]]:
    data = await _get_json(f"{YAHOO}/{symbol}", {"interval": interval, "range": rng})
    try:
        result = data["chart"]["result"][0]
        q = result["indicators"]["quote"][0]
        rows = zip(result["timestamp"], q["open"], q["high"], q["low"], q["close"])
        candles = [Candle(int(t), o, h, l, c) for t, o, h, l, c in rows if None not in (o, h, l, c)]
        return candles or None
    except (KeyError, IndexError, TypeError):
        return None


async def gold_candles_15m() -> Tuple[Optional[List[Candle]], str]:
    """Last ~2 days of 15m gold candles and the source name."""
    candles = await _cached("gold15", 60, lambda: _binance_candles("15m", 200))
    if candles:
        return candles, PAXG
    candles = await _cached("gold15k", 60, lambda: _kraken_candles(15))
    if candles:
        return candles, KRAKEN_PAXG
    candles = await _cached("gold15y", 60, lambda: _yahoo_candles("GC=F", "15m", "2d"))
    return (candles, COMEX) if candles else (None, "none")


async def gold_price() -> Tuple[Optional[float], str]:
    async def load() -> Optional[float]:
        data = await _get_json(f"{BINANCE}/ticker/price", {"symbol": "PAXGUSDT"})
        try:
            return float(data["price"])
        except (KeyError, TypeError, ValueError):
            return None

    price = await _cached("gold_px", 5, load)
    if price:
        return round(price, 2), PAXG
    candles, source = await gold_candles_15m()
    return (round(candles[-1].close, 2), source) if candles else (None, "none")


async def minute_candles(source: str, start: datetime, minutes: int) -> Optional[List[Candle]]:
    """1-minute candles from `start` (UTC) on the same instrument the plan was priced on — no caching."""
    if source == PAXG:
        candles = await _binance_candles("1m", min(minutes, 1000), start_ms=int(start.timestamp() * 1000))
    elif source == KRAKEN_PAXG:
        candles = await _kraken_candles(1, since=int(start.timestamp()) - 60)
    else:
        candles = await _yahoo_candles("GC=F", "1m", "5d")  # Yahoo keeps 1m data ~7 days
    if not candles:
        return None
    first = int(start.timestamp())
    return [c for c in candles if c.ts >= first][:minutes]


@dataclass(frozen=True)
class LevelsInput:
    price: float
    atr: float
    range_high: float
    range_low: float
    source: str


async def levels_input() -> Optional[LevelsInput]:
    """Live price, 15m ATR(14) and the last 4h (16 bars) range — None if data is unavailable."""
    candles, source = await gold_candles_15m()
    if not candles:
        return None
    # Price must come from the same feed as the candles (venues and futures differ by several dollars)
    price = (await gold_price())[0] if source == PAXG else round(candles[-1].close, 2)
    value = atr(candles, 14)
    rng = recent_range(candles, 16)
    if price is None or value is None or rng is None:
        return None
    return LevelsInput(price=price, atr=value, range_high=rng[0], range_low=rng[1], source=source)
