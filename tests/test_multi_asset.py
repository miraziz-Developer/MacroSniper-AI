import pytest
from app.engines.multi_asset_engine import multi_asset_engine, ASSET_REGISTRY


def test_asset_registry_specs():
    gold = multi_asset_engine.get_specs("XAUUSD")
    assert gold.category == "METALS"
    assert gold.usd_correlation < 0  # Inverse to USD

    usdjpy = multi_asset_engine.get_specs("USDJPY")
    assert usdjpy.category == "FOREX"
    assert usdjpy.usd_correlation > 0  # Aligned with USD

    us30 = multi_asset_engine.get_specs("US30")
    assert us30.category == "INDICES"
    assert us30.target_pips >= 4000


def test_asset_bias_calculation():
    # If total score is negative (-80):
    gold_bias = multi_asset_engine.calculate_asset_bias("XAUUSD", -80.0)
    assert "BEARISH" in gold_bias

    # If total score is positive (+80):
    usdjpy_bias = multi_asset_engine.calculate_asset_bias("USDJPY", 80.0)
    assert "BULLISH" in usdjpy_bias
