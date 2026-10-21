import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class IntermarketData:
    dxy_trend_pct: float       # Dollar Index momentum (e.g. +0.45%)
    us10y_yield_bps: float     # 10Y Treasury yield change in basis points (e.g. +6.5 bps)
    us2y_yield_bps: float      # 2Y Treasury yield (Fed rate expectations)
    crude_oil_pct: float       # WTI Crude oil change (Energy inflation driver)
    intermarket_score: float   # -100 (Strong Bearish USD / Bullish Gold) to +100 (Strong Bullish USD / Bearish Gold)
    summary: str


class IntermarketEngine:
    """
    T-30 Minutes Intermarket Correlation Engine:
    Tracks DXY, US 10-Year & 2-Year Bond Yields, and Energy inputs to measure
    intermarket capital flows before the Tier-1 release.
    """

    def evaluate_intermarket_flow(
        self,
        dxy_trend_pct: float = 0.35,      # +0.35% DXY strength
        us10y_yield_bps: float = 5.5,     # +5.5 bps yield spike
        us2y_yield_bps: float = 7.0,      # +7.0 bps short-end rate spike
        crude_oil_pct: float = 1.8,       # +1.8% oil strength
    ) -> IntermarketData:
        # 1. Yield Curve Momentum (Highest weight for Fed rate expectations)
        # 2Y yield is the most sensitive to Fed policy changes
        yield_score = (us2y_yield_bps * 5.0) + (us10y_yield_bps * 3.5)

        # 2. Dollar Index (DXY) Momentum
        dxy_score = dxy_trend_pct * 100.0 * 0.8

        # 3. Energy Factor (Crude oil pushes inflation expectations)
        oil_score = crude_oil_pct * 5.0

        # Weighted calculation of C_intermarket:
        raw_score = (yield_score * 0.50) + (dxy_score * 0.35) + (oil_score * 0.15)
        intermarket_score = max(-100.0, min(100.0, raw_score))

        direction = "USD KUCHAYISHI (XAUUSD/EURUSD SELL)" if intermarket_score > 0 else "USD ZAIFLASHISHI (XAUUSD/EURUSD BUY)"
        summary = (
            f"🌐 [INTERMARKET ENGINE]:\n"
            f"• DXY Momentum: {dxy_trend_pct:+0.2f}%\n"
            f"• US 10Y Yield: {us10y_yield_bps:+0.1f} bps | US 2Y Yield: {us2y_yield_bps:+0.1f} bps\n"
            f"• WTI Crude Energy: {crude_oil_pct:+0.1f}%\n"
            f"• Intermarket Score (C_inter): {intermarket_score:+0.1f}\n"
            f"Kutilma: {direction} tomoniga kapital oqimi kuchaymoqda."
        )

        return IntermarketData(
            dxy_trend_pct=dxy_trend_pct,
            us10y_yield_bps=us10y_yield_bps,
            us2y_yield_bps=us2y_yield_bps,
            crude_oil_pct=crude_oil_pct,
            intermarket_score=round(intermarket_score, 2),
            summary=summary,
        )


intermarket_engine = IntermarketEngine()
