"""Free historical XAUUSD minute candles from Dukascopy's public datafeed (one LZMA file per UTC day)."""

import asyncio
import lzma
import os
import struct
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

import httpx

URL = "https://datafeed.dukascopy.com/datafeed/XAUUSD/{y}/{m:02d}/{d:02d}/BID_candles_min_1.bi5"  # month is 0-based
RECORD = struct.Struct(">IIIIIf")  # seconds, open, close, low, high, volume; prices x1000


def _path(cache_dir: str, day: date) -> str:
    return os.path.join(cache_dir, f"{day:%Y%m%d}.bi5")


async def download_days(days: Iterable[date], cache_dir: str, concurrency: int = 4) -> int:
    """Downloads missing day files politely; returns how many were fetched."""
    os.makedirs(cache_dir, exist_ok=True)
    todo = [d for d in sorted(set(days)) if not os.path.exists(_path(cache_dir, d))]
    sem = asyncio.Semaphore(concurrency)
    fetched = 0

    async def one(client: httpx.AsyncClient, day: date) -> None:
        nonlocal fetched
        async with sem:
            for attempt in range(3):
                try:
                    res = await client.get(URL.format(y=day.year, m=day.month - 1, d=day.day))
                    if res.status_code == 200:
                        with open(_path(cache_dir, day), "wb") as f:
                            f.write(res.content)  # empty body = market closed, cached as such
                        fetched += 1
                        return
                    if res.status_code == 404:
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(2 * (attempt + 1))

    async with httpx.AsyncClient(timeout=30.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
        await asyncio.gather(*(one(client, d) for d in todo))
    return fetched


def load_day(cache_dir: str, day: date) -> Optional[Dict[datetime, tuple]]:
    """{minute_utc: (open, high, low, close)} or None when the file is missing/empty."""
    path = _path(cache_dir, day)
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    raw = lzma.decompress(open(path, "rb").read())
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    out: Dict[datetime, tuple] = {}
    for i in range(len(raw) // RECORD.size):
        sec, o, c, lo, hi, _vol = RECORD.unpack_from(raw, i * RECORD.size)
        out[start + timedelta(seconds=sec)] = (o / 1000, hi / 1000, lo / 1000, c / 1000)
    return out


def window(candles: Dict[datetime, tuple], start: datetime, minutes: int) -> List[tuple]:
    return [candles[t] for t in (start + timedelta(minutes=i) for i in range(minutes)) if t in candles]
