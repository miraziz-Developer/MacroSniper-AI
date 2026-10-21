"""T+0: turn the released number into a gold direction."""

from typing import Optional

from app.signals.rules import EventKind, gold_direction_for_usd


def resolve(kind: EventKind, actual: float, forecast: Optional[float], previous: Optional[float]) -> str:
    """BUY / SELL for gold, or INLINE when the number matches expectations."""
    baseline = forecast if forecast is not None else previous
    if baseline is None:
        return "INLINE"
    surprise = actual - baseline
    if abs(surprise) <= max(abs(baseline) * 0.001, 1e-9):
        return "INLINE"
    usd_up = (surprise > 0) == kind.usd_up_when_higher
    return gold_direction_for_usd(usd_up)
