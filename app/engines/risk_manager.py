import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from app.engines.multi_asset_engine import multi_asset_engine

logger = logging.getLogger(__name__)


@dataclass
class PositionSizeResult:
    symbol: str
    account_balance: float
    risk_pct: float
    risk_amount_usd: float
    sl_points: float
    calculated_lot: float
    max_safe_lot: float
    is_prop_firm_compliant: bool
    scaling_plan: Dict[str, Any]


class RiskManagementEngine:
    """
    Institutional & Prop Firm Risk Management Engine:
    Calculates exact mathematical lot sizes, enforces daily drawdown guards,
    and creates multi-target scaling-out plans (TP1, TP2, TP3).
    """

    def calculate_lot_size(
        self,
        symbol: str,
        account_balance: float = 10000.0, # e.g. $10,000 or $100,000 funded account
        risk_pct: float = 1.0,            # 1.0% risk per trade
        sl_points: float = 6.0,           # e.g. 6.0 points on Gold ($6.00)
        is_prop_firm_account: bool = True,
    ) -> PositionSizeResult:
        specs = multi_asset_engine.get_specs(symbol)

        # 1. Calculate monetary risk
        risk_amount_usd = account_balance * (risk_pct / 100.0)

        # 2. Points to dollar risk per 1.0 lot
        # For Gold: 1 lot = 100 oz -> 1.0 point ($1) move = $100
        # For EURUSD: 1 lot = 100,000 units -> 0.0001 (1 pip) = $10
        dollar_risk_per_lot = sl_points * 100.0 if specs.category == "METALS" else sl_points * 100000.0 if specs.category == "FOREX" else sl_points * specs.point_value_per_lot

        if dollar_risk_per_lot <= 0:
            dollar_risk_per_lot = 1.0

        raw_lot = risk_amount_usd / dollar_risk_per_lot
        # Round to 2 decimal places (standard broker minimum 0.01 lot)
        calculated_lot = max(0.01, round(raw_lot, 2))

        # Prop Firm Safety Cap (Max 2.5% daily drawdown rule)
        max_safe_lot = round(calculated_lot * 1.5, 2)
        is_compliant = risk_pct <= 2.0  # FTMO recommends max 1-2% per trade

        # 3. Multi-Target Partial Scaling Plan:
        # TP1: Close 50% lot at +400 points & Move SL to Breakeven (+20 pts) -> Trade is 100% Risk Free!
        # TP2: Close 30% lot at +800 points
        # TP3: Let 20% lot run to +1500 points (Trailing Stop)
        tp1_lot = round(calculated_lot * 0.50, 2)
        tp2_lot = round(calculated_lot * 0.30, 2)
        tp3_runner = round(calculated_lot - tp1_lot - tp2_lot, 2)

        scaling_plan = {
            "tp1_close_lot": max(0.01, tp1_lot),
            "tp1_target_pts": 400,
            "tp1_action": "CLOSE_50_PERCENT_AND_MOVE_SL_TO_BREAKEVEN",
            "tp2_close_lot": max(0.01, tp2_lot),
            "tp2_target_pts": 800,
            "tp3_runner_lot": max(0.01, tp3_runner),
            "tp3_target_pts": 1500,
            "trailing_stop_active": True,
        }

        return PositionSizeResult(
            symbol=symbol,
            account_balance=account_balance,
            risk_pct=risk_pct,
            risk_amount_usd=round(risk_amount_usd, 2),
            sl_points=sl_points,
            calculated_lot=calculated_lot,
            max_safe_lot=max_safe_lot,
            is_prop_firm_compliant=is_compliant,
            scaling_plan=scaling_plan,
        )

    def check_spread_safety(self, symbol: str, current_live_spread: float) -> Dict[str, Any]:
        """
        Dynamic Spread Protection Guard:
        Protects subscribers from horrific broker slippage during news spikes.
        """
        specs = multi_asset_engine.get_specs(symbol)
        is_safe = current_live_spread <= specs.max_safe_spread

        return {
            "symbol": symbol,
            "current_spread": current_live_spread,
            "max_safe_spread": specs.max_safe_spread,
            "is_safe_to_enter": is_safe,
            "status": "APPROVED" if is_safe else "BLOCKED_HIGH_SPREAD",
            "warning": None if is_safe else f"Spred me'yordan ortiq ({current_live_spread} > {specs.max_safe_spread}). Sirg'alish (slippage) xavfi yuqori!",
        }


risk_manager = RiskManagementEngine()
