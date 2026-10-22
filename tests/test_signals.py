from datetime import datetime, timezone

import pytest

from app.calendar.actuals import match_actual
from app.calendar.forexfactory import parse_items, parse_number, parse_unit
from app.market.indicators import Candle, atr, recent_range
from app.signals import history
from app.signals.outcome import resolve
from app.signals.plan import NEWS_SPREAD, build_plan, simulate
from app.signals.rules import classify


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


# Plan geometry (ATR=4): entries 0.3–0.8 ATR outside price (+$0.50 spread), SL 2 ATR, TP1 1.5R, TP2 3R
def test_plan_levels():
    p = build_plan(price=4140.0, atr=4.0, range_high=4142.0, range_low=4120.0)
    assert p.buy.entry == round(4142.0 + NEWS_SPREAD, 2)  # range high is 2.0 away (inside 1.2–3.2)
    assert p.sell.entry == round(4140.0 - 3.2 - NEWS_SPREAD, 2)  # range low too far -> capped at 0.8 ATR
    assert round(p.buy.entry - p.buy.sl, 2) == 8.0
    assert round(p.buy.tp1 - p.buy.entry, 2) == 12.0 and round(p.buy.tp2 - p.buy.entry, 2) == 24.0
    assert round(p.sell.sl - p.sell.entry, 2) == 8.0 and round(p.sell.entry - p.sell.tp2, 2) == 24.0


def test_plan_minimum_distance():
    p = build_plan(price=4140.0, atr=4.0, range_high=4140.5, range_low=4139.5)
    assert p.buy.entry == round(4140.0 + 1.2 + NEWS_SPREAD, 2)
    assert p.sell.entry == round(4140.0 - 1.2 - NEWS_SPREAD, 2)


def test_plan_rejects_bad_input():
    with pytest.raises(ValueError):
        build_plan(4140.0, 0.0, 4141, 4139)


FLAT = (4140.0, 4140.2, 4139.8, 4140.0)


def _plan():
    # buy 4142.5 / sl 4134.5 / tp1 4154.5 / tp2 4166.5 ; sell 4137.5 / sl 4145.5 / tp1 4125.5 / tp2 4113.5
    return build_plan(price=4140.0, atr=4.0, range_high=4142.0, range_low=4138.0)


def test_simulate_full_win_on_buy_side():
    candles = [(4140, 4143, 4140, 4142.8), (4143, 4155, 4142, 4154), (4154, 4167, 4150, 4166)] + [FLAT] * 120
    r = simulate(_plan(), candles, slippage=0.5)
    # entry 4143.0 (with slippage); tp1 4154.5 = +1.4375R, tp2 4166.5 = +2.9375R -> half each
    assert r == pytest.approx(0.5 * 11.5 / 8 + 0.5 * 23.5 / 8, abs=1e-3)


def test_simulate_stop_loss_and_whipsaw():
    loss = [(4140, 4143, 4140, 4141), (4141, 4141, 4134, 4135)] + [FLAT] * 120
    assert simulate(_plan(), loss, slippage=0.5) == pytest.approx((4134.5 - 4143.0) / 8, abs=1e-3)
    whipsaw = [(4140, 4150, 4130, 4140)] + [FLAT] * 120
    assert simulate(_plan(), whipsaw, slippage=0.5) == pytest.approx(-1.0 - 1.0 / 8, abs=1e-3)


def test_simulate_break_even_after_tp1_and_cancel_and_pending():
    be = [(4137, 4138, 4137, 4137), (4137, 4137, 4125, 4126), (4126, 4146, 4126, 4140)] + [FLAT] * 120
    # sell filled 4137.0, TP1 4125.5 -> +1.4375R on half, rest stopped at entry -> 0
    assert simulate(_plan(), be, slippage=0.5) == pytest.approx(0.5 * 11.5 / 8, abs=1e-3)
    assert simulate(_plan(), [FLAT] * 40, slippage=0.5) == 0.0  # never triggered -> cancelled
    assert simulate(_plan(), [FLAT] * 10, slippage=0.5) is None  # too early to tell


def test_simulate_time_stop_closes_open_trade():
    candles = [(4140, 4143, 4140, 4143)] + [(4145, 4146, 4144, 4145)] * 119
    assert simulate(_plan(), candles, slippage=0.5) == pytest.approx((4145 - 4143.0) / 8, abs=1e-3)


def test_history_drives_which_releases_get_plans():
    assert history.is_plannable("Non-Farm Employment Change")
    assert not history.is_plannable("Unemployment Claims")
    assert history.reaction("Non-Farm Employment Change")["n"] > 50


def _candles(closes):
    return [Candle(i, c, c + 1, c - 1, c) for i, c in enumerate(closes)]


def test_indicators():
    candles = _candles([100.0] * 20)
    assert atr(candles, 14) == pytest.approx(2.0)
    assert atr(candles[:10], 14) is None
    assert recent_range(candles, 4) == (101.0, 99.0)


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


async def test_calendar_falls_back_to_mirror_when_feed_is_blocked(monkeypatch):
    from app.calendar import forexfactory as ff

    feed = [{"title": "CPI m/m", "country": "USD", "date": "2026-10-21T08:30:00-04:00", "impact": "High"}]
    calls = []

    class Res:
        def __init__(self, code, body):
            self.status_code, self._body = code, body

        def json(self):
            return self._body

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url):
            calls.append(url)
            return Res(403, None) if url == ff.FEED_URL else Res(200, feed)

    monkeypatch.setattr(ff, "_memory", [])
    monkeypatch.setattr(ff.httpx, "AsyncClient", FakeClient)
    items = await ff.fetch_week()
    assert [i.title for i in items] == ["CPI m/m"]
    assert calls == [ff.FEED_URL, ff.settings.CALENDAR_MIRROR_URL]


async def test_gold_feed_falls_back_binance_kraken_comex(monkeypatch):
    from app.market import data

    rows = [[1_700_000_000 + i * 900, "4090", "4092", "4088", str(4090 + i * 0.1), "4090", "1", 3] for i in range(20)]
    yahoo = {"chart": {"result": [{"timestamp": [1, 2], "indicators": {"quote": [{
        "open": [4100, 4101], "high": [4102, 4103], "low": [4099, 4100], "close": [4101, 4102]}]}}]}}
    up = {"binance": False, "kraken": True}

    async def fake_get_json(url, params=None):
        if "binance" in url:
            return None if not up["binance"] else [[0, "1", "1", "1", "1"]]
        if "kraken" in url:
            return {"error": [], "result": {"PAXGUSD": rows, "last": 0}} if up["kraken"] else None
        return yahoo

    monkeypatch.setattr(data, "_get_json", fake_get_json)
    monkeypatch.setattr(data, "_cache", {})
    candles, source = await data.gold_candles_15m()
    assert source == data.KRAKEN_PAXG and len(candles) == 20 and candles[-1].close == 4091.9
    levels = await data.levels_input()
    assert levels.source == data.KRAKEN_PAXG and levels.price == 4091.9  # price from the same feed

    up["kraken"] = False
    monkeypatch.setattr(data, "_cache", {})
    assert (await data.gold_candles_15m())[1] == data.COMEX
