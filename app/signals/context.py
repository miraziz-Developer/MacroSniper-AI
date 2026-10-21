"""T-3h context: how the market is positioned going into the release (real DXY / yields / gold data)."""

from dataclasses import dataclass, field
from typing import List, Optional

from app.market.data import MacroSnapshot
from app.signals.rules import EventKind


@dataclass
class Context:
    gold_score: float  # -100 (strong SELL) .. +100 (strong BUY)
    bias: str  # BUY / SELL / NEUTRAL
    reasons: List[str] = field(default_factory=list)
    data_points: int = 0  # how many real inputs were available


def _clip(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


def build_context(
    kind: EventKind,
    forecast: Optional[float],
    previous: Optional[float],
    snap: MacroSnapshot,
    threshold: float,
) -> Context:
    usd = 0.0  # positive = USD strength pressure
    reasons: List[str] = []
    points = 0

    # 1) Expectation: forecast vs previous, signed by how this release moves the dollar
    if forecast is not None and previous is not None and previous != forecast:
        rel = (forecast - previous) / max(abs(previous), 1e-9)
        signed = rel if kind.usd_up_when_higher else -rel
        part = _clip(signed * 400.0, 30.0)
        usd += part
        points += 1
        word = "yuqori" if forecast > previous else "past"
        effect = "USD foydasiga" if part > 0 else "USD zarariga"
        reasons.append(f"Prognoz ({forecast:g}) avvalgidan ({previous:g}) {word} — {effect}")

    # 2) Dollar momentum over 5 sessions
    if snap.dxy_5d_pct is not None:
        part = _clip(snap.dxy_5d_pct * 25.0, 35.0)
        usd += part
        points += 1
        reasons.append(f"DXY 5 kunda {snap.dxy_5d_pct:+.2f}%")

    # 3) US 10Y yield trend
    if snap.us10y_5d_bps is not None:
        part = _clip(snap.us10y_5d_bps * 1.5, 35.0)
        usd += part
        points += 1
        reasons.append(f"AQSH 10 yillik daromadliligi 5 kunda {snap.us10y_5d_bps:+.0f} bps")

    gold = round(_clip(-usd, 100.0), 1)
    if snap.gold_5d_pct is not None:
        reasons.append(f"Oltin 5 kunda {snap.gold_5d_pct:+.2f}%")

    if points < 2:
        bias = "NEUTRAL"
        reasons.append("Ma'lumot yetarli emas — yo'nalish berilmaydi")
    elif gold >= threshold:
        bias = "BUY"
    elif gold <= -threshold:
        bias = "SELL"
    else:
        bias = "NEUTRAL"
    return Context(gold_score=gold, bias=bias, reasons=reasons, data_points=points)
