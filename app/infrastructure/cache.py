import asyncio
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class CatalogCacheService:
    def __init__(
        self,
        *,
        backend: str,
        redis_url: str | None,
        ttl_seconds: int,
        namespace: str = "reghub:catalog",
    ) -> None:
        self.requested_backend = backend
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds
        self.namespace = namespace
        self.backend_name = "disabled"
        self._redis: Any | None = None
        self._memory: dict[str, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()
        self._generation = 1

    async def initialize(self) -> None:
        if self.ttl_seconds <= 0 or self.requested_backend == "disabled":
            self.backend_name = "disabled"
            return
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
                logger.warning("Redis catalog cache unavailable; using in-memory cache")
        self.backend_name = "memory"

    async def _degrade_to_memory(self, operation: str) -> None:
        logger.exception("Redis catalog cache %s failed; degrading to in-memory cache", operation)
        client = self._redis
        self._redis = None
        self.backend_name = "memory"
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                logger.debug("Failed to close degraded Redis cache client", exc_info=True)

    async def _generation_value(self) -> int:
        if self.backend_name == "redis" and self._redis is not None:
            try:
                key = f"{self.namespace}:generation"
                value = await self._redis.get(key)
                if value is None:
                    await self._redis.set(key, "1", nx=True)
                    return 1
                try:
                    return int(value)
                except (TypeError, ValueError):
                    await self._redis.set(key, "1")
                    return 1
            except Exception:
                await self._degrade_to_memory("generation lookup")
        return self._generation

    async def get_json(self, key: str) -> Any | None:
        if self.backend_name == "disabled":
            return None
        generation = await self._generation_value()
        namespaced = f"{self.namespace}:v{generation}:{key}"
        if self.backend_name == "redis" and self._redis is not None:
            try:
                value = await self._redis.get(namespaced)
                if not value:
                    return None
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    await self._redis.delete(namespaced)
                    return None
            except Exception:
                await self._degrade_to_memory("read")
                return None
        async with self._lock:
            item = self._memory.get(namespaced)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= time.monotonic():
                self._memory.pop(namespaced, None)
                return None
            return value

    async def set_json(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        if self.backend_name == "disabled":
            return
        ttl = self.ttl_seconds if ttl_seconds is None else max(1, ttl_seconds)
        generation = await self._generation_value()
        namespaced = f"{self.namespace}:v{generation}:{key}"
        if self.backend_name == "redis" and self._redis is not None:
            try:
                await self._redis.set(
                    namespaced,
                    json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str),
                    ex=ttl,
                )
                return
            except Exception:
                await self._degrade_to_memory("write")
        async with self._lock:
            self._memory[namespaced] = (time.monotonic() + ttl, value)
            if len(self._memory) > 5000:
                now = time.monotonic()
                self._memory = {
                    item_key: item for item_key, item in self._memory.items() if item[0] > now
                }

    async def invalidate_all(self) -> None:
        if self.backend_name == "redis" and self._redis is not None:
            try:
                await self._redis.incr(f"{self.namespace}:generation")
                return
            except Exception:
                await self._degrade_to_memory("invalidation")
        async with self._lock:
            self._generation += 1
            self._memory.clear()

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
