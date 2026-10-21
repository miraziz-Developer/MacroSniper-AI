import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any
from app.core.config import settings
from app.engines.multi_asset_engine import multi_asset_engine
from app.engines.risk_manager import risk_manager

logger = logging.getLogger(__name__)


@dataclass
class SniperOrder:
    symbol: str
    bias: str                     # "BULLISH (BUY)" or "BEARISH (SELL)" or "NO_TRADE"
    confidence: int               # 0 - 100%
    is_tradable: bool             # False if |S_total| < 40 (Safety filter)
    total_score: float

    # Limit Trap (Judas Swing / Liquidity hunt catcher)
    limit_trap_type: str          # "SELL_LIMIT" or "BUY_LIMIT"
    limit_trap_price: float
    limit_sl: float
    limit_tp: float               # Main TP
    limit_tp1: float              # +400 pts (Close 50% & Move to Breakeven)
    limit_tp2: float              # +800 pts
    limit_tp3: float              # +1500 pts (Runner)

    # Momentum Breakout Stop Order (Direct explosion without fake-out)
    stop_break_type: str          # "SELL_STOP" or "BUY_STOP"
    stop_break_price: float
    stop_sl: float
    stop_tp: float

    # Risk & Scaling Plan
    recommended_lot: float
    summary: str


class SniperDecisionEngine:
    """
    T-2 Minutes (4:58) Pre-Sniper Engine:
    Combines F_macro (45%), T_liquidity (35%), and C_intermarket (20%) into S_total.
    Supports multi-asset execution across Gold, Forex, Indices, and Energy.
    """

    def calculate_total_score(
        self,
        macro_score: float,        # F_macro (-100 to +100)
        liquidity_score: float,    # T_liquidity (-100 to +100)
        intermarket_score: float,  # C_intermarket (-100 to +100)
    ) -> float:
        total = (0.45 * macro_score) + (0.35 * liquidity_score) + (0.20 * intermarket_score)
        return round(total, 2)

    def generate_pre_sniper_signal(
        self,
        macro_score: float,
        liquidity_zones: Dict[str, float],
        current_price: float,
        atr_m15: float,
        intermarket_score: float = 0.0,
        symbol: str = "XAUUSD",
        spread_buffer: Optional[float] = None,
        account_balance: float = 10000.0,
        risk_pct: float = 1.0,
    ) -> SniperOrder:
        """
        Generates 4:58 Pre-News Trap and Breakout orders with multi-target scaling plan.
        """
        specs = multi_asset_engine.get_specs(symbol)
        buffer = spread_buffer if spread_buffer is not None else specs.typical_news_spread
        total_score = self.calculate_total_score(macro_score, liquidity_zones.get("liquidity_score", 0.0), intermarket_score)

        # Calculate decimal precision (Forex 4 decimals, Gold/Indices 2 decimals)
        precision = 4 if specs.category == "FOREX" else 2

        # Deposit Protection Rule:
        if abs(total_score) < settings.MEDIUM_CONVICTION_THRESHOLD:
            logger.info(f"Signal score {total_score} is below threshold ({settings.MEDIUM_CONVICTION_THRESHOLD}). NO PRE-TRADE.")
            return SniperOrder(
                symbol=symbol,
                bias="NEUTRAL (NO PRE-TRADE)",
                confidence=int(abs(total_score)),
                is_tradable=False,
                total_score=total_score,
                limit_trap_type="NONE",
                limit_trap_price=0.0,
                limit_sl=0.0,
                limit_tp=0.0,
                limit_tp1=0.0,
                limit_tp2=0.0,
                limit_tp3=0.0,
                stop_break_type="NONE",
                stop_break_price=0.0,
                stop_sl=0.0,
                stop_tp=0.0,
                recommended_lot=0.0,
                summary=(
                    f"🛡️ NO PRE-TRADE ZONE (Score: {total_score:+0.1f}).\n"
                    f"Signallar o'rtasidagi nomuvofiqlik tufayli depozitni asrash uchun yangilikdan oldin order qo'yilmaydi. "
                    f"Yangilik chiqqach, 3-daqiqadagi tasdiq kutiladi."
                ),
            )

        # Determine directional bias accounting for USD correlation
        bias_str = multi_asset_engine.calculate_asset_bias(symbol, total_score)
        is_bullish = "BULLISH" in bias_str or "BUY" in bias_str
        confidence = min(95, int(abs(macro_score) * 0.85 + 15))

        upper_ob = liquidity_zones.get("upper_ob", current_price + (atr_m15 * 1.5))
        lower_ob = liquidity_zones.get("lower_ob", current_price - (atr_m15 * 1.5))

        if not is_bullish:
            # ==========================================================
            # MAIN EXPECTATION: BEARISH (SELL)
            # ==========================================================
            # 1. SELL LIMIT Trap: Catches the initial Judas Swing fake spike to upper liquidity
            trap_entry = round(max(upper_ob, current_price + (atr_m15 * 1.3)), precision)
            trap_sl = round(trap_entry + (atr_m15 * 1.2) + buffer, precision)
            trap_tp = round(trap_entry - (atr_m15 * 3.5), precision)
            trap_tp1 = round(trap_entry - (atr_m15 * 1.0), precision)
            trap_tp2 = round(trap_entry - (atr_m15 * 2.2), precision)
            trap_tp3 = round(trap_entry - (atr_m15 * 4.0), precision)

            # 2. SELL STOP Breakout: If price collapses instantly without upward fake spike
            break_entry = round(current_price - (atr_m15 * 0.8) - buffer, precision)
            break_sl = round(current_price + (atr_m15 * 0.6), precision)
            break_tp = round(break_entry - (atr_m15 * 3.0), precision)

            # Calculate Prop Firm position size
            sl_dist = abs(trap_entry - trap_sl)
            risk_calc = risk_manager.calculate_lot_size(symbol, account_balance, risk_pct, sl_dist)

            summary = (
                f"🎯 [4:58 PRE-SNIPER SIGNAL — {symbol}]:\n"
                f"• Direction: BEARISH (SELL) | Confidence: {confidence}%\n"
                f"• Judas Swing Trap: SELL LIMIT @ {trap_entry} (SL: {trap_sl} | TP: {trap_tp})\n"
                f"  - TP1 (Scale 50% & Breakeven): {trap_tp1}\n"
                f"  - TP2 (Scale 30%): {trap_tp2}\n"
                f"  - TP3 Runner: {trap_tp3}\n"
                f"• Momentum Breakout: SELL STOP @ {break_entry} (SL: {break_sl} | TP: {break_tp})\n"
                f"• Tavsiya etilgan Lot: {risk_calc.calculated_lot} (Risk: ${risk_calc.risk_amount_usd} / {risk_pct}%)\n"
                f"• Spred Buffer: +{buffer} pts"
            )

            return SniperOrder(
                symbol=symbol,
                bias="BEARISH (SELL)",
                confidence=confidence,
                is_tradable=True,
                total_score=total_score,
                limit_trap_type="SELL_LIMIT",
                limit_trap_price=trap_entry,
                limit_sl=trap_sl,
                limit_tp=trap_tp,
                limit_tp1=trap_tp1,
                limit_tp2=trap_tp2,
                limit_tp3=trap_tp3,
                stop_break_type="SELL_STOP",
                stop_break_price=break_entry,
                stop_sl=break_sl,
                stop_tp=break_tp,
                recommended_lot=risk_calc.calculated_lot,
                summary=summary,
            )

        else:
            # ==========================================================
            # MAIN EXPECTATION: BULLISH (BUY)
            # ==========================================================
            # 1. BUY LIMIT Trap: Catches downward Judas Swing stop hunt
            trap_entry = round(min(lower_ob, current_price - (atr_m15 * 1.3)), precision)
            trap_sl = round(trap_entry - (atr_m15 * 1.2) - buffer, precision)
            trap_tp = round(trap_entry + (atr_m15 * 3.5), precision)
            trap_tp1 = round(trap_entry + (atr_m15 * 1.0), precision)
            trap_tp2 = round(trap_entry + (atr_m15 * 2.2), precision)
            trap_tp3 = round(trap_entry + (atr_m15 * 4.0), precision)

            # 2. BUY STOP Breakout: If price rockets directly upward
            break_entry = round(current_price + (atr_m15 * 0.8) + buffer, precision)
            break_sl = round(current_price - (atr_m15 * 0.6), precision)
            break_tp = round(break_entry + (atr_m15 * 3.0), precision)

            sl_dist = abs(trap_entry - trap_sl)
            risk_calc = risk_manager.calculate_lot_size(symbol, account_balance, risk_pct, sl_dist)

            summary = (
                f"🎯 [4:58 PRE-SNIPER SIGNAL — {symbol}]:\n"
                f"• Direction: BULLISH (BUY) | Confidence: {confidence}%\n"
                f"• Judas Swing Trap: BUY LIMIT @ {trap_entry} (SL: {trap_sl} | TP: {trap_tp})\n"
                f"  - TP1 (Scale 50% & Breakeven): {trap_tp1}\n"
                f"  - TP2 (Scale 30%): {trap_tp2}\n"
                f"  - TP3 Runner: {trap_tp3}\n"
                f"• Momentum Breakout: BUY STOP @ {break_entry} (SL: {break_sl} | TP: {break_tp})\n"
                f"• Tavsiya etilgan Lot: {risk_calc.calculated_lot} (Risk: ${risk_calc.risk_amount_usd} / {risk_pct}%)\n"
                f"• Spred Buffer: +{buffer} pts"
            )

            return SniperOrder(
                symbol=symbol,
                bias="BULLISH (BUY)",
                confidence=confidence,
                is_tradable=True,
                total_score=total_score,
                limit_trap_type="BUY_LIMIT",
                limit_trap_price=trap_entry,
                limit_sl=trap_sl,
                limit_tp=trap_tp,
                limit_tp1=trap_tp1,
                limit_tp2=trap_tp2,
                limit_tp3=trap_tp3,
                stop_break_type="BUY_STOP",
                stop_break_price=break_entry,
                stop_sl=break_sl,
                stop_tp=break_tp,
                recommended_lot=risk_calc.calculated_lot,
                summary=summary,
            )


sniper_engine = SniperDecisionEngine()
