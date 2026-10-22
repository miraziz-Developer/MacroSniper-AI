"""T-2m OCO straddle plan and its minute-by-minute evaluation (shared by the live review and research/analyze.py).

Parameters were tuned on 2012–2020 NFP/CPI releases and validated on 2021–2025 (research/REPORT.md).
"""

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

NEWS_SPREAD = 0.50  # $ buffer for widened spreads at release time
ENTRY_MIN_ATR = 0.3  # entries just outside the pre-news range, at least this many ATRs away...
ENTRY_MAX_ATR = 0.8  # ...and at most this many
SL_ATR = 2.0  # stop distance = 1R
TP1_R = 1.5  # close half, move stop to entry
TP2_R = 3.0  # close the rest
CANCEL_AFTER_MIN = 30  # untriggered orders are cancelled after this many minutes
TIME_STOP_MIN = 120  # an open position is closed at market this many minutes after the release

Candle = Tuple[float, float, float, float]  # open, high, low, close (1-minute)


@dataclass(frozen=True)
class Side:
    entry: float
    sl: float
    tp1: float
    tp2: float


@dataclass(frozen=True)
class TradePlan:
    price: float
    atr: float
    range_high: float
    range_low: float
    buy: Side
    sell: Side


def build_plan(
    price: float,
    atr: float,
    range_high: float,
    range_low: float,
    entry_min: float = ENTRY_MIN_ATR,
    entry_max: float = ENTRY_MAX_ATR,
    sl_atr: float = SL_ATR,
    tp1_r: float = TP1_R,
    tp2_r: float = TP2_R,
) -> TradePlan:
    if atr <= 0 or price <= 0:
        raise ValueError("price and ATR must be positive")
    up = min(max(range_high - price, entry_min * atr), entry_max * atr) + NEWS_SPREAD
    down = min(max(price - range_low, entry_min * atr), entry_max * atr) + NEWS_SPREAD
    risk = sl_atr * atr
    b, s = price + up, price - down
    r = lambda v: round(v, 2)  # noqa: E731
    return TradePlan(
        price=r(price),
        atr=r(atr),
        range_high=r(range_high),
        range_low=r(range_low),
        buy=Side(r(b), r(b - risk), r(b + tp1_r * risk), r(b + tp2_r * risk)),
        sell=Side(r(s), r(s + risk), r(s - tp1_r * risk), r(s - tp2_r * risk)),
    )


def simulate(plan: TradePlan, candles: Sequence[Candle], slippage: float = 0.5) -> Optional[float]:
    """Result in R from 1-minute candles starting at the release minute.

    Conservative: a minute that touches both orders, or both stop and target, resolves against us.
    Returns None when there are not yet enough candles to decide.
    """
    risk = plan.buy.entry - plan.buy.sl
    side = 0
    for i, (_o, high, low, close) in enumerate(candles[:TIME_STOP_MIN]):
        if side == 0:
            if i >= CANCEL_AFTER_MIN:
                return 0.0
            hit_buy, hit_sell = high >= plan.buy.entry, low <= plan.sell.entry
            if hit_buy and hit_sell:
                return round(-1.0 - 2 * slippage / risk, 3)  # whipsaw through both orders in one minute
            if not (hit_buy or hit_sell):
                continue
            side = 1 if hit_buy else -1
            leg = plan.buy if hit_buy else plan.sell
            entry = leg.entry + side * slippage
            stop, tp1, tp2 = leg.sl, leg.tp1, leg.tp2
            half_done = False
        adverse, favour = (low, high) if side == 1 else (high, low)
        if (adverse - stop) * side <= 0:
            exit_r = (stop - entry) * side / risk
            return round(0.5 * (tp1 - entry) * side / risk + 0.5 * exit_r if half_done else exit_r, 3)
        if not half_done and (favour - tp1) * side >= 0:
            half_done, stop = True, entry
        if half_done and (favour - tp2) * side >= 0:
            return round(0.5 * (tp1 - entry) * side / risk + 0.5 * (tp2 - entry) * side / risk, 3)
        if i == TIME_STOP_MIN - 1:
            open_r = (close - entry) * side / risk
            return round(0.5 * (tp1 - entry) * side / risk + 0.5 * open_r if half_done else open_r, 3)
    return None  # not enough candles yet
