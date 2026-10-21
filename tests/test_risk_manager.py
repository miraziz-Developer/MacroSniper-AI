import pytest
from app.engines.risk_manager import risk_manager
from app.engines.intermarket_engine import intermarket_engine


def test_position_sizing_calculation():
    # $10,000 account, 1% risk ($100), SL distance 6.50 points on Gold
    result = risk_manager.calculate_lot_size(
        symbol="XAUUSD",
        account_balance=10000.0,
        risk_pct=1.0,
        sl_points=6.50,
    )

    assert result.risk_amount_usd == 100.0
    assert result.calculated_lot > 0.0
    assert result.is_prop_firm_compliant is True
    assert "tp1_close_lot" in result.scaling_plan
    assert result.scaling_plan["tp1_action"] == "CLOSE_50_PERCENT_AND_MOVE_SL_TO_BREAKEVEN"


def test_spread_protection_guard():
    # Normal Gold spread 1.80 -> Safe to enter
    safe_check = risk_manager.check_spread_safety("XAUUSD", 1.80)
    assert safe_check["is_safe_to_enter"] is True
    assert safe_check["status"] == "APPROVED"

    # Extreme news spread 6.50 points (Broker widening) -> Block entry!
    danger_check = risk_manager.check_spread_safety("XAUUSD", 6.50)
    assert danger_check["is_safe_to_enter"] is False
    assert danger_check["status"] == "BLOCKED_HIGH_SPREAD"


def test_intermarket_flow_calculation():
    data = intermarket_engine.evaluate_intermarket_flow(
        dxy_trend_pct=0.45,
        us10y_yield_bps=6.5,
        us2y_yield_bps=8.0,
        crude_oil_pct=2.1,
    )
    assert data.intermarket_score > 40.0  # Strong positive USD score
    assert "DXY Momentum" in data.summary
