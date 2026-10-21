import pytest
from app.engines.sniper_decision import sniper_engine, SniperOrder


def test_bearish_sniper_order_generation():
    """
    Test pre-sniper formula for BEARISH macro bias (Gold Sell / USD rally).
    """
    # Negative macro score (-80) + negative liquidity sweep
    macro_score = -80.0
    liquidity_zones = {
        "upper_ob": 2662.00,
        "lower_ob": 2638.00,
        "liquidity_score": -40.0,
    }
    current_price = 2650.00
    atr_m15 = 4.50
    intermarket_score = -30.0

    signal = sniper_engine.generate_pre_sniper_signal(
        macro_score=macro_score,
        liquidity_zones=liquidity_zones,
        current_price=current_price,
        atr_m15=atr_m15,
        intermarket_score=intermarket_score,
        symbol="XAUUSD",
        spread_buffer=1.80,
    )

    assert signal.is_tradable is True
    assert "BEARISH" in signal.bias
    assert signal.confidence >= 65
    assert signal.limit_trap_type == "SELL_LIMIT"
    # Limit trap entry should be at upper liquidity block or current + atr*1.3
    assert signal.limit_trap_price >= current_price
    assert signal.limit_sl > signal.limit_trap_price
    assert signal.limit_tp < signal.limit_trap_price
    # Stop breakout entry should be below current price
    assert signal.stop_break_type == "SELL_STOP"
    assert signal.stop_break_price < current_price


def test_bullish_sniper_order_generation():
    """
    Test pre-sniper formula for BULLISH macro bias (Gold Buy / USD weakness).
    """
    macro_score = 75.0
    liquidity_zones = {
        "upper_ob": 2665.00,
        "lower_ob": 2635.00,
        "liquidity_score": 50.0,
    }
    current_price = 2650.00
    atr_m15 = 4.50

    signal = sniper_engine.generate_pre_sniper_signal(
        macro_score=macro_score,
        liquidity_zones=liquidity_zones,
        current_price=current_price,
        atr_m15=atr_m15,
        intermarket_score=20.0,
        symbol="XAUUSD",
    )

    assert signal.is_tradable is True
    assert "BULLISH" in signal.bias
    assert signal.limit_trap_type == "BUY_LIMIT"
    assert signal.limit_trap_price <= current_price
    assert signal.limit_sl < signal.limit_trap_price
    assert signal.limit_tp > signal.limit_trap_price
    assert signal.stop_break_type == "BUY_STOP"
    assert signal.stop_break_price > current_price


def test_neutral_deposit_protection_filter():
    """
    Test that low score (|S_total| < 40) triggers NO PRE-TRADE filter.
    """
    macro_score = 10.0
    liquidity_zones = {"liquidity_score": -10.0}
    current_price = 2650.00
    atr_m15 = 4.50

    signal = sniper_engine.generate_pre_sniper_signal(
        macro_score=macro_score,
        liquidity_zones=liquidity_zones,
        current_price=current_price,
        atr_m15=atr_m15,
        intermarket_score=0.0,
    )

    assert signal.is_tradable is False
    assert "NO PRE-TRADE" in signal.bias
