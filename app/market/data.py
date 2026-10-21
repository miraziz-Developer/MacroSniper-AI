"""Free market data: Binance PAXG (tracks spot gold, 24/7) with Yahoo Finance as fallback/macro source."""

import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import httpx

from app.market.indicators import Candle, atr, pct_change, recent_range

logger = logging.getLogger(__name__)

BINANCE = "https://api.binance.com/api/v3"
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart"
HEADERS = {"User-Agent": "Mozilla/5.0 (MacroSniper)"}
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


async def _binance_candles(interval: str, limit: int) -> Optional[List[Candle]]:
    data = await _get_json(f"{BINANCE}/klines", {"symbol": "PAXGUSDT", "interval": interval, "limit": limit})
    if not isinstance(data, list) or not data:
        return None
    try:
        return [Candle(int(k[0]) // 1000, float(k[1]), float(k[2]), float(k[3]), float(k[4])) for k in data]
    except (IndexError, TypeError, ValueError):
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
        return candles, "Binance PAXG"
    candles = await _cached("gold15y", 60, lambda: _yahoo_candles("GC=F", "15m", "2d"))
    return (candles, "COMEX GC=F") if candles else (None, "none")


async def gold_price() -> Tuple[Optional[float], str]:
    async def load() -> Optional[float]:
        data = await _get_json(f"{BINANCE}/ticker/price", {"symbol": "PAXGUSDT"})
        try:
            return float(data["price"])
        except (KeyError, TypeError, ValueError):
            return None

    price = await _cached("gold_px", 5, load)
    if price:
        return round(price, 2), "Binance PAXG"
    candles, source = await gold_candles_15m()
    return (round(candles[-1].close, 2), source) if candles else (None, "none")


async def _daily_closes(symbol: str) -> Optional[List[float]]:
    candles = await _cached(f"d1:{symbol}", 900, lambda: _yahoo_candles(symbol, "1d", "1mo"))
    return [c.close for c in candles] if candles else None


@dataclass(frozen=True)
class MacroSnapshot:
    dxy_1d_pct: Optional[float]
    dxy_5d_pct: Optional[float]
    us10y_1d_bps: Optional[float]
    us10y_5d_bps: Optional[float]
    gold_5d_pct: Optional[float]


def _bps_change(closes: Optional[List[float]], lookback: int) -> Optional[float]:
    # ^TNX is quoted in percent (4.25 = 4.25%), so 1 point = 100 bps
    if not closes or len(closes) <= lookback:
        return None
    return (closes[-1] - closes[-1 - lookback]) * 100.0


async def macro_snapshot() -> MacroSnapshot:
    dxy = await _daily_closes("DX-Y.NYB")
    tnx = await _daily_closes("^TNX")
    gold = await _daily_closes("GC=F")
    return MacroSnapshot(
        dxy_1d_pct=pct_change(dxy, 1) if dxy else None,
        dxy_5d_pct=pct_change(dxy, 5) if dxy else None,
        us10y_1d_bps=_bps_change(tnx, 1),
        us10y_5d_bps=_bps_change(tnx, 5),
        gold_5d_pct=pct_change(gold, 5) if gold else None,
    )


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
    # Price must come from the same instrument as the candles (PAXG and GC=F differ by several dollars)
    price = (await gold_price())[0] if source == "Binance PAXG" else round(candles[-1].close, 2)
    value = atr(candles, 14)
    rng = recent_range(candles, 16)
    if price is None or value is None or rng is None:
        return None
    return LevelsInput(price=price, atr=value, range_high=rng[0], range_low=rng[1], source=source)
