import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class SafetyEvaluationResult:
    is_confirmed: bool                # True = forecast matched actual release
    is_kill_switch_triggered: bool   # True = opposite data shock detected!
    action: str                       # "HOLD_TARGETS", "EMERGENCY_CANCEL_AND_FLIP", "STAND_BY"
    headline: str
    message: str
    suggested_flip_order: Optional[Dict[str, Any]] = None


class SafetyGuardEngine:
    """
    T+1s (5:00:01) Instant Verification & Kill-Switch Engine:
    Validates the released actual number against the pre-sniper prediction
    within 1 second to either confirm the mega-trend or immediately cancel & flip.
    """

    def evaluate_release(
        self,
        event_title: str,
        predicted_bias: str,          # "BEARISH (SELL)" or "BULLISH (BUY)"
        actual: float,
        forecast: float,
        previous: Optional[float] = None,
        current_price: Optional[float] = None,
        symbol: str = "XAUUSD",
    ) -> SafetyEvaluationResult:
        deviation = round(actual - forecast, 4)
        title_lower = event_title.lower()

        # Determine whether high actual is positive or negative for the asset
        # For USD macro indicators (CPI, NFP, PPI, Retail Sales):
        # Higher Actual than Forecast = USD Bullish -> Gold (XAUUSD) Bearish
        # Lower Actual than Forecast = USD Bearish -> Gold (XAUUSD) Bullish
        is_usd_positive = deviation > 0
        actual_asset_bias = "BEARISH (SELL)" if is_usd_positive else "BULLISH (BUY)"

        # Check for matching vs opposing shock
        predicted_is_bullish = "BULLISH" in predicted_bias
        actual_is_bullish = "BULLISH" in actual_asset_bias

        deviation_str = f"Actual: {actual} vs Forecast: {forecast} (Deviation: {deviation:+0.2f})"

        # Case 1: In-line or Strong Confirmation (75% probability)
        if predicted_is_bullish == actual_is_bullish:
            logger.info(f"✅ SAFETY CONFIRMATION: {deviation_str}. Prediction confirmed!")
            headline = "✅ ACTUAL DATA CONFIRMED!"
            message = (
                f"✅ **ACTUAL DATA CONFIRMED!**\n"
                f"📊 {event_title}\n"
                f"• {deviation_str}\n"
                f"🎯 **Tahlil 100% tasdiqlandi!** {predicted_bias} orderlarni ushlab turing, maqsad: **+1000 pips**!"
            )
            return SafetyEvaluationResult(
                is_confirmed=True,
                is_kill_switch_triggered=False,
                action="HOLD_TARGETS",
                headline=headline,
                message=message,
            )

        # Case 2: DATA SHOCK / ANOMALY - Opposing surprise detected!
        else:
            logger.warning(f"⚠️ KILL SWITCH ACTIVATED: {deviation_str}. Opposite shock!")
            flip_direction = "BUY" if not predicted_is_bullish else "SELL"
            flip_price = current_price or 0.0
            
            # Flip parameters
            flip_tp = round(flip_price + 15.0 if flip_direction == "BUY" else flip_price - 15.0, 2)
            flip_sl = round(flip_price - 5.0 if flip_direction == "BUY" else flip_price + 5.0, 2)

            flip_order = {
                "action": f"MARKET_{flip_direction}",
                "symbol": symbol,
                "price": flip_price,
                "tp": flip_tp,
                "sl": flip_sl,
            }

            headline = "⚠️ DATA SHOCK — KILL-SWITCH TRIGGERED!"
            message = (
                f"🚨 **DATA SHOCK (TESKARI RAQAM CHIQDI)!**\n"
                f"📊 {event_title}\n"
                f"• {deviation_str}\n"
                f"🛑 **QAT'IY BUYRUQ:**\n"
                f"1. Avval qo'yilgan barcha Limit va Stop orderlarni **DARHOL BEKOR QILING (CANCEL)**!\n"
                f"2. Yangi bozor tezligi teskari tomonga yo'naldi: **Marketdan {flip_direction} {symbol}**!\n"
                f"🎯 Yangi Target: {flip_tp:.2f} | SL: {flip_sl:.2f}"
            )

            return SafetyEvaluationResult(
                is_confirmed=False,
                is_kill_switch_triggered=True,
                action="EMERGENCY_CANCEL_AND_FLIP",
                headline=headline,
                message=message,
                suggested_flip_order=flip_order,
            )


safety_guard = SafetyGuardEngine()
