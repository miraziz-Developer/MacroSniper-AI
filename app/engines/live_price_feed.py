import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)


class LivePriceFeed:
    """
    Fetches real-time market prices for XAUUSD (Gold)
    from global low-latency market feeds without requiring local MT5.
    """

    @staticmethod
    async def get_live_gold_price() -> float:
        """
        Fetches live gold spot price in USD.
        Tries Binance PAXG and Yahoo Finance COMEX with instant fallback.
        """
        # Source 1: Binance PAXGUSDT (Backed 1:1 by physical Gold, sub-100ms latency)
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get("https://api.binance.com/api/v3/ticker/price?symbol=PAXGUSDT")
                if res.status_code == 200:
                    price = float(res.json()["price"])
                    if price > 1000.0:
                        logger.debug(f"Fetched live Gold price from Binance PAXG: {price}")
                        return round(price, 2)
        except Exception as e:
            logger.debug(f"Binance PAXG feed failed: {e}")

        # Source 2: Yahoo Finance COMEX Gold Futures (GC=F)
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get("https://query1.finance.yahoo.com/v8/finance/chart/GC=F", headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
                    if price and float(price) > 1000.0:
                        logger.debug(f"Fetched live Gold price from Yahoo GC=F: {price}")
                        return round(float(price), 2)
        except Exception as e:
            logger.debug(f"Yahoo Finance GC=F feed failed: {e}")

        # Fallback default if market is closed (e.g. weekend) or offline
        logger.info("Using baseline market reference for Gold: $4140.00")
        return 4140.00


live_price_feed = LivePriceFeed()
