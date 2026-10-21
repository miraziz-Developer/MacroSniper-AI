import pytest
from PIL import Image
from app.services.card_renderer import card_renderer


def test_render_pre_sniper_card():
    card_bytes = card_renderer.render_pre_sniper_card(
        event_title="US Consumer Price Index (CPI) YoY",
        bias="BEARISH (SELL)",
        confidence=88,
        current_price=2650.00,
        limit_type="SELL_LIMIT",
        limit_entry=2658.50,
        limit_sl=2665.70,
        limit_tp=2642.00,
        stop_type="SELL_STOP",
        stop_entry=2645.20,
        stop_sl=2652.70,
        stop_tp=2631.00,
        total_score=-78.5,
        symbol="XAUUSD",
    )

    assert card_bytes is not None
    img = Image.open(card_bytes)
    assert img.size == (card_renderer.WIDTH, card_renderer.HEIGHT)
    assert img.format == "PNG"


def test_render_safety_alert_card():
    card_bytes = card_renderer.render_safety_alert_card(
        event_title="US CPI YoY",
        is_confirmed=True,
        actual=3.4,
        forecast=3.1,
        headline="ACTUAL DATA CONFIRMED!",
        action_message="Hold targets for +1000 pips move!",
        symbol="XAUUSD",
    )

    assert card_bytes is not None
    img = Image.open(card_bytes)
    assert img.size == (card_renderer.WIDTH, card_renderer.HEIGHT)
    assert img.format == "PNG"
