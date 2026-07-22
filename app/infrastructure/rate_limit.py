import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int


class RateLimitService:
    def __init__(self, *, backend: str, redis_url: str | None) -> None:
        self.requested_backend = backend
        self.redis_url = redis_url
        self.backend_name = "memory"
        self._redis: Any | None = None
        self._memory: dict[str, tuple[int, int]] = {}
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        wants_redis = self.requested_backend == "redis" or (
            self.requested_backend == "auto" and bool(self.redis_url)
        )
        if wants_redis and self.redis_url:
            try:
                from redis.asyncio import Redis

                client = Redis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=3,
                    socket_timeout=3,
                )
                await client.ping()
                self._redis = client
                self.backend_name = "redis"
                return
            except Exception:
                if self.requested_backend == "redis":
                    raise
                logger.warning("Redis rate limiter unavailable; using in-memory limits")
        self.backend_name = "memory"

    async def _degrade_to_memory(self) -> None:
        logger.exception("Redis rate limiter failed; degrading to in-memory limits")
        client = self._redis
        self._redis = None
        self.backend_name = "memory"
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                logger.debug("Failed to close degraded Redis rate-limit client", exc_info=True)

    @staticmethod
    def safe_identifier(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]

    async def _memory_check(
        self, key: str, *, window_start: int, limit: int, retry_after: int, window: int
    ) -> RateLimitResult:
        async with self._lock:
            count, existing_window = self._memory.get(key, (0, window_start))
            if existing_window != window_start:
                count = 0
            count += 1
            self._memory[key] = (count, window_start)
            if len(self._memory) > 20_000:
                threshold = window_start - window * 2
                self._memory = {
                    item_key: item
                    for item_key, item in self._memory.items()
                    if item[1] >= threshold
                }
        return RateLimitResult(
            allowed=count <= limit,
            limit=limit,
            remaining=max(0, limit - count),
            retry_after=retry_after,
        )

    async def check(
        self, bucket: str, identifier: str, limit: int, window: int = 60
    ) -> RateLimitResult:
        now = int(time.time())
        window_start = now - (now % window)
        retry_after = max(1, window - (now - window_start))
        key = f"reghub:rate:{bucket}:{self.safe_identifier(identifier)}:{window_start}"
        if self.backend_name == "redis" and self._redis is not None:
            try:
                pipe = self._redis.pipeline(transaction=True)
                pipe.incr(key)
                pipe.expire(key, window + 2, nx=True)
                count, _ = await pipe.execute()
                count = int(count)
                return RateLimitResult(
                    allowed=count <= limit,
                    limit=limit,
                    remaining=max(0, limit - count),
                    retry_after=retry_after,
                )
            except Exception:
                await self._degrade_to_memory()
        return await self._memory_check(
            key,
            window_start=window_start,
            limit=limit,
            retry_after=retry_after,
            window=window,
        )

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
