import pytest
from app.services.telegram_sender import telegram_notifier
from app.services.mt5_copier import mt5_bridge


@pytest.mark.asyncio
async def test_telegram_sender_simulation_mode():
    """Verify methods return cleanly in simulation / test environment."""
    morning = await telegram_notifier.send_morning_calendar_alert(
        event_title="US Non-Farm Payrolls",
        event_time_str="17:30 UTC+5",
    )
    # Should not throw any exception
    assert isinstance(morning, bool)

    macro = await telegram_notifier.send_t3h_macro_scan(
        event_title="US Non-Farm Payrolls",
        macro_score=65.0,
        summary_text="Labor market strong",
    )
    assert isinstance(macro, bool)

    signal = await telegram_notifier.send_458_sniper_signal(
        event_title="US Non-Farm Payrolls",
        symbol="XAUUSD",
        bias="BEARISH (SELL)",
        confidence=85,
        limit_type="SELL_LIMIT",
        limit_price=2658.0,
        limit_sl=2665.0,
        limit_tp=2638.0,
        stop_type="SELL_STOP",
        stop_price=2645.0,
        stop_sl=2652.0,
        stop_tp=2630.0,
    )
    assert isinstance(signal, bool)


@pytest.mark.asyncio
async def test_mt5_copier_bridge():
    orders = await mt5_bridge.place_sniper_bracket_orders(
        symbol="XAUUSD",
        limit_type="SELL_LIMIT",
        limit_price=2658.00,
        limit_sl=2665.00,
        limit_tp=2638.00,
        stop_type="SELL_STOP",
        stop_price=2645.00,
        stop_sl=2652.00,
        stop_tp=2630.00,
    )
    assert orders["status"] == "placed"
    assert "limit_ticket" in orders

    cancel_res = await mt5_bridge.emergency_kill_switch_cancel_all("XAUUSD")
    assert cancel_res["status"] == "cancelled"

    flip_res = await mt5_bridge.execute_market_flip("XAUUSD", "BUY", sl=2645.0, tp=2670.0)
    assert flip_res["status"] == "executed"
