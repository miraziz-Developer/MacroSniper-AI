"""T-2m straddle plan from real 15m ATR and the pre-news range."""

from dataclasses import dataclass
from typing import Optional

NEWS_SPREAD = 0.50  # $ buffer for widened spreads at release time


@dataclass(frozen=True)
class Side:
    entry: float
    sl: float
    tp1: float  # 1R — take half, move SL to entry
    tp2: float  # 2R


@dataclass(frozen=True)
class TradePlan:
    price: float
    atr: float
    range_high: float
    range_low: float
    buy: Side
    sell: Side
    primary: Optional[str]  # BUY / SELL / None (no conviction: breakout only)


def build_plan(price: float, atr: float, range_high: float, range_low: float, bias: str) -> TradePlan:
    if atr <= 0 or price <= 0:
        raise ValueError("price and ATR must be positive")
    # Entries just outside the pre-news range, but never closer than 0.5 ATR nor further than 2 ATR
    up = min(max(range_high - price, 0.5 * atr), 2.0 * atr) + NEWS_SPREAD
    down = min(max(price - range_low, 0.5 * atr), 2.0 * atr) + NEWS_SPREAD
    risk = 1.5 * atr

    buy_entry = price + up
    sell_entry = price - down
    r = lambda v: round(v, 2)  # noqa: E731
    buy = Side(r(buy_entry), r(buy_entry - risk), r(buy_entry + risk), r(buy_entry + 2 * risk))
    sell = Side(r(sell_entry), r(sell_entry + risk), r(sell_entry - risk), r(sell_entry - 2 * risk))
    return TradePlan(
        price=r(price),
        atr=r(atr),
        range_high=r(range_high),
        range_low=r(range_low),
        buy=buy,
        sell=sell,
        primary=bias if bias in ("BUY", "SELL") else None,
    )
