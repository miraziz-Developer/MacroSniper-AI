"""Load the historical ForexFactory calendar (Hugging Face: Tropstan/Forex_Factory_Calendar) into clean USD releases.

The scrape loses the time of events that share a release slot (they show up as 00:00 local), so the
release time is taken from each series' official New York schedule instead of the file.
"""

import re
from datetime import date, datetime, time
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

NY = ZoneInfo("America/New_York")

# FF event name -> (series key, New York release time, higher actual => stronger USD)
SERIES = {
    "CPI m/m": ("cpi", time(8, 30), True),
    "Core CPI m/m": ("core_cpi", time(8, 30), True),
    "Non-Farm Employment Change": ("nfp", time(8, 30), True),
    "Unemployment Rate": ("unemployment", time(8, 30), False),
    "Average Hourly Earnings m/m": ("ahe", time(8, 30), True),
    "Unemployment Claims": ("claims", time(8, 30), False),
    "Retail Sales m/m": ("retail", time(8, 30), True),
    "Core Retail Sales m/m": ("core_retail", time(8, 30), True),
    "PPI m/m": ("ppi", time(8, 30), True),
    "Core PPI m/m": ("core_ppi", time(8, 30), True),
    "Core PCE Price Index m/m": ("core_pce", time(8, 30), True),
    "ADP Non-Farm Employment Change": ("adp", time(8, 15), True),
    "ISM Manufacturing PMI": ("ism_mfg", time(10, 0), True),
    "ISM Services PMI": ("ism_svc", time(10, 0), True),
    "Federal Funds Rate": ("fed_rate", time(14, 0), True),
}

_NUM = re.compile(r"[-+]?\d*\.?\d+")
_SCALE = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


def parse_value(raw) -> Optional[float]:
    """'228K' -> 228000, '0.3%' -> 0.3, '' -> None (series keep consistent units)."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    text = str(raw).strip()
    m = _NUM.search(text)
    if not m:
        return None
    value = float(m.group(0))
    for suffix, scale in _SCALE.items():
        if text.endswith(suffix):
            return value * scale
    return value


def release_time_utc(local_date: date, ny_time: time) -> datetime:
    return datetime.combine(local_date, ny_time, tzinfo=NY).astimezone(ZoneInfo("UTC"))


def load_releases(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, usecols=["DateTime", "Currency", "Event", "Actual", "Forecast", "Previous"])
    df = df[(df.Currency == "USD") & df.Event.isin(SERIES)].copy()
    # The calendar date in the file's own timezone (Tehran) is the US release date for these slots
    df["local_date"] = df.DateTime.str.slice(0, 10).map(date.fromisoformat)
    meta = df.Event.map(SERIES)
    df["series"] = meta.map(lambda m: m[0])
    df["usd_up_when_higher"] = meta.map(lambda m: m[2])
    df["release_utc"] = [release_time_utc(d, SERIES[e][1]) for d, e in zip(df.local_date, df.Event)]
    for col in ("Actual", "Forecast", "Previous"):
        df[col.lower()] = df[col].map(parse_value)
    df = df.dropna(subset=["actual", "forecast"])
    df = df.drop_duplicates(subset=["series", "local_date"]).sort_values("release_utc").reset_index(drop=True)
    df["surprise"] = df.actual - df.forecast
    sign = df.surprise.apply(lambda s: 0 if abs(s) < 1e-12 else (1 if s > 0 else -1))
    # +1: USD-positive surprise (=> gold expected down), -1: USD-negative, 0: in line
    df["usd_surprise"] = sign * df.usd_up_when_higher.map({True: 1, False: -1})
    return df[
        ["release_utc", "local_date", "series", "Event", "actual", "forecast", "previous", "surprise", "usd_surprise"]
    ]
