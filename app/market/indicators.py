from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Candle:
    ts: int  # unix seconds, candle open
    open: float
    high: float
    low: float
    close: float


def atr(candles: Sequence[Candle], period: int = 14) -> Optional[float]:
    """Simple-average ATR over the last `period` true ranges; None if not enough data."""
    if len(candles) < period + 1:
        return None
    trs: List[float] = []
    for prev, cur in zip(candles[-period - 1 : -1], candles[-period:]):
        trs.append(max(cur.high - cur.low, abs(cur.high - prev.close), abs(cur.low - prev.close)))
    return sum(trs) / period


def recent_range(candles: Sequence[Candle], bars: int) -> Optional[Tuple[float, float]]:
    """(high, low) of the last `bars` candles."""
    window = candles[-bars:]
    if not window:
        return None
    return max(c.high for c in window), min(c.low for c in window)
