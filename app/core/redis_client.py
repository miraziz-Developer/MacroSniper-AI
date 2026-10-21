import time
import logging
from typing import Optional, Any
import redis.asyncio as aioredis
from app.core.config import settings

logger = logging.getLogger(__name__)


class InMemoryCache:
    """Fallback in-memory cache when Redis server is not accessible."""

    def __init__(self):
        self._store: dict[str, tuple[Any, Optional[float]]] = {}

    async def get(self, key: str) -> Optional[str]:
        if key in self._store:
            val, expire_at = self._store[key]
            if expire_at is not None and time.time() > expire_at:
                del self._store[key]
                return None
            return val
        return None

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        expire_at = (time.time() + ex) if ex else None
        self._store[key] = (value, expire_at)
        return True

    async def delete(self, key: str) -> int:
        if key in self._store:
            del self._store[key]
            return 1
        return 0

    async def exists(self, key: str) -> int:
        val = await self.get(key)
        return 1 if val is not None else 0

    async def ping(self) -> bool:
        return True

    async def close(self):
        self._store.clear()


class CacheClient:
    def __init__(self):
        self.client = None
        self.is_fallback = False

    async def connect(self):
        try:
            r = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=0.5,
            )
            await r.ping()
            self.client = r
            self.is_fallback = False
            logger.info("Connected to Redis server successfully.")
        except Exception as e:
            logger.debug(f"Redis unavailable ({e}). Using In-Memory Cache.")
            self.client = InMemoryCache()
            self.is_fallback = True

    async def get(self, key: str) -> Optional[str]:
        if not self.client:
            await self.connect()
        try:
            return await self.client.get(key)
        except Exception:
            self.client = InMemoryCache()
            self.is_fallback = True
            return await self.client.get(key)

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        if not self.client:
            await self.connect()
        try:
            return await self.client.set(key, value, ex=ex)
        except Exception:
            self.client = InMemoryCache()
            self.is_fallback = True
            return await self.client.set(key, value, ex=ex)

    async def delete(self, key: str) -> int:
        if not self.client:
            await self.connect()
        try:
            return await self.client.delete(key)
        except Exception:
            self.client = InMemoryCache()
            self.is_fallback = True
            return await self.client.delete(key)

    async def ping(self) -> bool:
        if not self.client:
            await self.connect()
        try:
            return await self.client.ping()
        except Exception:
            self.client = InMemoryCache()
            self.is_fallback = True
            return True

    async def close(self):
        if self.client:
            try:
                await self.client.close()
            except Exception:
                pass


cache = CacheClient()
