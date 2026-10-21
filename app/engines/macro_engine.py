import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MacroAnalysisResult:
    macro_score: float         # -100 (Strong Bearish USD / Bullish Gold) to +100 (Strong Bullish USD / Bearish Gold)
    bias_summary: str          # Text explanation for Telegram briefing
    leading_factors: Dict[str, Any]
    confidence_pct: int


class MacroEngine:
    """
    T-3 Hours Fundamental Engine:
    Evaluates leading macro indicators (ADP, ISM, Jobless Claims, Yields, PPI)
    and estimates fundamental pressure before the Tier-1 release.
    """

    def analyze_event(
        self,
        event_title: str,
        forecast: Optional[float],
        previous: Optional[float],
        leading_data: Optional[Dict[str, float]] = None,
    ) -> MacroAnalysisResult:
        title_lower = event_title.lower()
        leading = leading_data or {}

        # 1. Non-Farm Payrolls (NFP) leading analysis
        if "non-farm" in title_lower or "nfp" in title_lower:
            adp_surprise = leading.get("adp_surprise", 15.0)       # e.g. +15k over forecast
            ism_employment = leading.get("ism_employment", 52.0)   # > 50 expansion
            jobless_trend = leading.get("jobless_claims_trend", -5.0) # lower claims = strong labor

            # Score calculation: Positive means strong USD, negative for Gold (XAUUSD)
            score = (adp_surprise * 0.3) + ((ism_employment - 50.0) * 4.0 * 0.4) + (-jobless_trend * 0.3)
            # Clamp between -100 and +100
            macro_score = max(-100.0, min(100.0, score * 3.0))
            
            direction = "USD KUCHAYISHI (XAUUSD SELL)" if macro_score > 0 else "USD ZAIFLASHISHI (XAUUSD BUY)"
            summary = (
                f"🧠 [T-3h Macro Scan - NFP]:\n"
                f"• ADP Surprise: {adp_surprise:+0.1f}K\n"
                f"• ISM Employment: {ism_employment:.1f}\n"
                f"• Macro Score: {macro_score:+0.1f}\n"
                f"Kutilma: {direction} ehtimoli {min(92, int(abs(macro_score) * 0.6 + 40))}%."
            )

        # 2. CPI (Inflation) leading analysis
        elif "cpi" in title_lower or "inflation" in title_lower or "consumer price" in title_lower:
            ppi_yoy = leading.get("ppi_yoy_trend", 0.3)               # PPI leads CPI by 1 month
            ism_prices_paid = leading.get("ism_prices_paid", 54.0)    # Raw materials inflation
            oil_momentum = leading.get("oil_monthly_pct", 2.5)       # Energy component

            score = (ppi_yoy * 100 * 0.35) + ((ism_prices_paid - 50.0) * 3.5 * 0.45) + (oil_momentum * 2.0 * 0.20)
            macro_score = max(-100.0, min(100.0, score * 2.0))

            direction = "INFLYATSIYA YUQORI (XAUUSD SELL)" if macro_score > 0 else "INFLYATSIYA PASAYISHI (XAUUSD BUY)"
            summary = (
                f"🧠 [T-3h Macro Scan - CPI]:\n"
                f"• PPI Leading Trend: {ppi_yoy:+0.2f}%\n"
                f"• ISM Prices Paid: {ism_prices_paid:.1f}\n"
                f"• Energy Factor: {oil_momentum:+0.1f}%\n"
                f"• Macro Score: {macro_score:+0.1f}\n"
                f"Kutilma: {direction} (Inflyatsiya bosimi yuqori)."
            )

        # 3. FOMC / Interest Rates
        elif "fomc" in title_lower or "interest rate" in title_lower:
            fedwatch_hike_prob = leading.get("fedwatch_hawkish_prob", 65.0) # 0-100%
            us10y_yield_trend = leading.get("us10y_trend_bps", 6.0)         # basis points

            macro_score = (fedwatch_hike_prob - 50.0) * 1.5 + (us10y_yield_trend * 3.0)
            macro_score = max(-100.0, min(100.0, macro_score))

            direction = "HAWKISH FED (USD BUY / XAUUSD SELL)" if macro_score > 0 else "DOVISH FED (USD SELL / XAUUSD BUY)"
            summary = (
                f"🧠 [T-3h Macro Scan - FOMC]:\n"
                f"• Hawkish Probability: {fedwatch_hike_prob:.1f}%\n"
                f"• 10Y Yield Momentum: {us10y_yield_trend:+0.1f} bps\n"
                f"• Macro Score: {macro_score:+0.1f}\n"
                f"Kutilma: {direction}."
            )

        # Default generic macroeconomic evaluation
        else:
            diff = (forecast - previous) if (forecast is not None and previous is not None) else 0.0
            macro_score = max(-100.0, min(100.0, diff * 20.0))
            summary = f"🧠 [T-3h Macro Scan]: Standard event evaluation. Score: {macro_score:+0.1f}"

        confidence = min(95, int(abs(macro_score) * 0.75 + 20))
        return MacroAnalysisResult(
            macro_score=round(macro_score, 2),
            bias_summary=summary,
            leading_factors=leading,
            confidence_pct=confidence,
        )


macro_engine = MacroEngine()
