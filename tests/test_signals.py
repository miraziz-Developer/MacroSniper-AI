from datetime import datetime, timezone

import pytest

from app.calendar.actuals import match_actual
from app.calendar.forexfactory import parse_items, parse_number, parse_unit
from app.market.data import MacroSnapshot
from app.market.indicators import Candle, atr, pct_change, recent_range
from app.signals.context import build_context
from app.signals.outcome import resolve
from app.signals.plan import NEWS_SPREAD, build_plan
from app.signals.rules import classify

EMPTY = MacroSnapshot(None, None, None, None, None)


@pytest.mark.parametrize(
    "title,key",
    [
        ("Unemployment Claims", "claims"),
        ("Unemployment Rate", "unemployment"),
        ("Non-Farm Employment Change", "nfp"),
        ("ADP Non-Farm Employment Change", "adp"),
        ("Core CPI m/m", "cpi"),
        ("Core PCE Price Index m/m", "pce"),
        ("Federal Funds Rate", "rate"),
        ("ISM Services PMI", "pmi"),
        ("Advance GDP q/q", "gdp"),
    ],
)
def test_classify_known_releases(title, key):
    assert classify(title).key == key


@pytest.mark.parametrize("title", ["FOMC Member Waller Speaks", "Fed Chair Powell Testifies", "FOMC Meeting Minutes", "Bank Holiday"])
def test_classify_rejects_non_numeric_events(title):
    assert classify(title) is None


def test_outcome_direction_per_kind():
    cpi, claims = classify("CPI m/m"), classify("Unemployment Claims")
    assert resolve(cpi, 0.4, 0.3, 0.2) == "SELL"  # hot inflation -> USD up -> gold down
    assert resolve(cpi, 0.2, 0.3, 0.2) == "BUY"
    assert resolve(claims, 240, 225, 220) == "BUY"  # more claims -> USD down -> gold up
    assert resolve(cpi, 0.3, 0.3, 0.2) == "INLINE"
    assert resolve(cpi, 0.3, None, 0.2) == "SELL"  # falls back to previous
    assert resolve(cpi, 0.3, None, None) == "INLINE"


def test_context_needs_real_data_before_naming_a_side():
    ctx = build_context(classify("CPI m/m"), 0.4, 0.2, EMPTY, threshold=50)
    assert ctx.bias == "NEUTRAL" and ctx.data_points == 1


def test_context_strong_usd_gives_gold_sell():
    snap = MacroSnapshot(dxy_1d_pct=0.3, dxy_5d_pct=1.5, us10y_1d_bps=4, us10y_5d_bps=25, gold_5d_pct=-1.0)
    ctx = build_context(classify("CPI m/m"), 0.4, 0.2, snap, threshold=50)
    assert ctx.bias == "SELL" and ctx.gold_score <= -50
    assert any("DXY" in r for r in ctx.reasons)


def test_context_weak_usd_and_rising_claims_gives_gold_buy():
    snap = MacroSnapshot(dxy_1d_pct=-0.4, dxy_5d_pct=-1.6, us10y_1d_bps=-5, us10y_5d_bps=-22, gold_5d_pct=2.0)
    ctx = build_context(classify("Unemployment Claims"), 240, 220, snap, threshold=50)
    assert ctx.bias == "BUY" and ctx.gold_score >= 50


def test_context_mixed_signals_stay_neutral():
    snap = MacroSnapshot(None, 0.8, None, -10, None)
    ctx = build_context(classify("CPI m/m"), 0.3, 0.3, snap, threshold=50)
    assert ctx.bias == "NEUTRAL"


def test_plan_levels_are_symmetric_risk_and_outside_range():
    p = build_plan(price=4140.0, atr=4.0, range_high=4145.0, range_low=4132.0, bias="NEUTRAL")
    assert p.primary is None
    assert p.buy.entry == round(4145.0 + NEWS_SPREAD, 2)
    assert p.sell.entry == round(4140.0 - 8.0 - NEWS_SPREAD, 2)  # range low is 8 away = the 2 ATR cap
    assert round(p.buy.entry - p.buy.sl, 2) == 6.0 == round(p.buy.tp1 - p.buy.entry, 2)
    assert round(p.sell.sl - p.sell.entry, 2) == 6.0 == round(p.sell.entry - p.sell.tp1, 2)
    assert round(p.buy.tp2 - p.buy.entry, 2) == 12.0


def test_plan_minimum_distance_and_primary_side():
    p = build_plan(price=4140.0, atr=4.0, range_high=4140.5, range_low=4139.5, bias="BUY")
    assert p.primary == "BUY"
    assert p.buy.entry == round(4140.0 + 2.0 + NEWS_SPREAD, 2)  # at least 0.5 ATR away


def test_plan_rejects_bad_input():
    with pytest.raises(ValueError):
        build_plan(4140.0, 0.0, 4141, 4139, "BUY")


def _candles(closes):
    return [Candle(i, c, c + 1, c - 1, c) for i, c in enumerate(closes)]


def test_indicators():
    candles = _candles([100.0] * 20)
    assert atr(candles, 14) == pytest.approx(2.0)
    assert atr(candles[:10], 14) is None
    assert recent_range(candles, 4) == (101.0, 99.0)
    assert pct_change([100.0, 101.0, 102.0], 2) == pytest.approx(2.0)
    assert pct_change([100.0], 5) is None


def test_forexfactory_parsing():
    items = parse_items(
        [
            {"title": "CPI m/m", "country": "USD", "date": "2026-10-21T08:30:00-04:00", "impact": "High", "forecast": "0.3%", "previous": "0.2%"},
            {"title": "Unemployment Claims", "country": "USD", "date": "2026-10-22T08:30:00-04:00", "impact": "High", "forecast": "225K", "previous": ""},
            {"title": "IMF Meetings", "country": "All", "date": "2026-10-22T08:30:00-04:00", "impact": "Low"},
            {"title": "Broken", "country": "USD", "date": "not-a-date"},
        ]
    )
    assert len(items) == 2
    cpi, claims = items
    assert cpi.event_time == datetime(2026, 10, 21, 12, 30, tzinfo=timezone.utc)
    assert (cpi.forecast, cpi.previous, cpi.unit) == (0.3, 0.2, "%")
    assert (claims.forecast, claims.previous, claims.unit) == (225.0, None, "K")
    assert cpi.external_id == "FF_USD_CPI_m_m_202610211230"
    assert parse_number("-1.5B") == -1.5 and parse_number("") is None and parse_unit("12M") == "M"


def test_fmp_actual_match_and_rescale():
    t = datetime(2026, 10, 22, 12, 30, tzinfo=timezone.utc)
    items = [
        {"country": "US", "event": "Initial Jobless Claims", "date": "2026-10-22 12:30:00", "actual": 231000, "previous": 220000},
        {"country": "US", "event": "CPI MoM", "date": "2026-10-22 12:30:00", "actual": 0.4, "previous": 0.2},
    ]
    assert match_actual("Unemployment Claims", t, 220.0, items) == pytest.approx(231.0)
    assert match_actual("CPI m/m", t, 0.2, items) == pytest.approx(0.4)
    assert match_actual("CPI m/m", t.replace(hour=14), 0.2, items) is None  # time mismatch
    assert match_actual("FOMC Member Speaks", t, None, items) is None
