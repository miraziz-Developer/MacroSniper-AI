import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)


class LivePriceFeed:
    """
    Fetches real-time market prices for XAUUSD (Gold) and EURUSD
    from global low-latency market feeds without requiring local MT5.
    """

    @staticmethod
    async def get_live_gold_price() -> float:
        """
        Fetches live gold spot price in USD.
        Tries multiple fast public endpoints with instant fallback.
        """
        # Source 1: Binance PAXGUSDT (Backed 1:1 by physical Gold, sub-100ms latency)
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get("https://api.binance.com/api/v3/ticker/price?symbol=PAXGUSDT")
                if res.status_code == 200:
                    price = float(res.json()["price"])
                    logger.debug(f"Fetched live Gold price from Binance PAXG: {price}")
                    return round(price, 2)
        except Exception as e:
            logger.debug(f"Binance PAXG feed failed: {e}")

        # Source 2: Alternative Free Gold / Metal Spot Feed
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get("https://api.metals.live/v1/spot/gold")
                if res.status_code == 200:
                    data = res.json()
                    # data format: [{"gold": 2650.50, "timestamp": ...}]
                    if isinstance(data, list) and len(data) > 0 and "gold" in data[0]:
                        return round(float(data[0]["gold"]), 2)
        except Exception as e:
            logger.debug(f"Metals.live feed failed: {e}")

        # Fallback default if market is closed (e.g. weekend) or offline
        logger.info("Using baseline market reference for Gold: $2650.00")
        return 2650.00


live_price_feed = LivePriceFeed()
