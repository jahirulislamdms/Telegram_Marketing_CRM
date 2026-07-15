"""Fixed-window per-client rate limiter.

Backed by Redis when reachable (so limits are shared across API workers), with an
in-process fallback for single-process/dev runs and tests. The limiter is a
counter over a fixed time window: the first request in a window sets the counter
with a TTL; subsequent requests increment it until the window rolls over.
"""

import threading
import time

import redis.asyncio as aioredis

from app.config import settings


class _MemoryStore:
    """Process-local fixed-window counters. Thread-safe; good enough for one worker."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key -> (count, window_expires_at_epoch)
        self._buckets: dict[str, tuple[int, float]] = {}

    def hit(self, key: str, limit: int, window: int, now: float) -> tuple[bool, int, int]:
        with self._lock:
            count, expires = self._buckets.get(key, (0, 0.0))
            if now >= expires:
                count, expires = 0, now + window
            count += 1
            self._buckets[key] = (count, expires)
            remaining = max(0, limit - count)
            retry_after = max(1, int(round(expires - now)))
            return count <= limit, remaining, retry_after

    def clear(self) -> None:  # pragma: no cover - test helper
        with self._lock:
            self._buckets.clear()


class RateLimiter:
    def __init__(self) -> None:
        self._memory = _MemoryStore()
        self._redis: aioredis.Redis | None = None
        self._redis_ok = False

    async def startup(self) -> None:
        try:
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
            await self._redis.ping()
            self._redis_ok = True
        except Exception:  # noqa: BLE001 - any failure -> in-process fallback
            self._redis_ok = False

    async def shutdown(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:  # noqa: BLE001
                pass

    async def hit(self, key: str, limit: int, window: int) -> tuple[bool, int, int]:
        """Register one request against ``key``.

        Returns ``(allowed, remaining, retry_after_seconds)``.
        """
        now = time.time()
        if self._redis_ok and self._redis is not None:
            try:
                redis_key = f"ratelimit:{key}"
                count = await self._redis.incr(redis_key)
                if count == 1:
                    await self._redis.expire(redis_key, window)
                    ttl = window
                else:
                    ttl = await self._redis.ttl(redis_key)
                    if ttl < 0:  # no expiry set (edge case) -> reset it
                        await self._redis.expire(redis_key, window)
                        ttl = window
                remaining = max(0, limit - count)
                return count <= limit, remaining, max(1, int(ttl))
            except Exception:  # noqa: BLE001 - fall back to memory on Redis error
                self._redis_ok = False
        return self._memory.hit(key, limit, window, now)


limiter = RateLimiter()
