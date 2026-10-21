import pytest
from app.engines.safety_guard import safety_guard


def test_safety_guard_actual_confirmed():
    """
    Scenario 1: Actual data matches prediction (e.g. CPI high -> XAUUSD SELL).
    """
    result = safety_guard.evaluate_release(
        event_title="US Consumer Price Index (CPI) YoY",
        predicted_bias="BEARISH (SELL)",
        actual=3.4,
        forecast=3.1,
        previous=3.0,
        current_price=2650.00,
        symbol="XAUUSD",
    )

    assert result.is_confirmed is True
    assert result.is_kill_switch_triggered is False
    assert result.action == "HOLD_TARGETS"
    assert "ACTUAL DATA CONFIRMED" in result.headline


def test_safety_guard_kill_switch_triggered():
    """
    Scenario 2: Data shock (actual is opposite of expectation).
    AI expected SELL, but CPI came in much lower (2.7% vs 3.1%).
    System must trigger Kill-Switch in < 1 second and issue flip BUY order!
    """
    result = safety_guard.evaluate_release(
        event_title="US Consumer Price Index (CPI) YoY",
        predicted_bias="BEARISH (SELL)",
        actual=2.7,
        forecast=3.1,
        previous=3.0,
        current_price=2650.00,
        symbol="XAUUSD",
    )

    assert result.is_confirmed is False
    assert result.is_kill_switch_triggered is True
    assert result.action == "EMERGENCY_CANCEL_AND_FLIP"
    assert "KILL-SWITCH TRIGGERED" in result.headline
    assert result.suggested_flip_order is not None
    assert result.suggested_flip_order["action"] == "MARKET_BUY"
