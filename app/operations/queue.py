import json
from typing import Any
from uuid import UUID


class RedisOperationQueue:
    def __init__(
        self,
        redis_url: str,
        *,
        queue_name: str,
        lock_ttl_seconds: int,
        poll_seconds: float,
    ) -> None:
        self.redis_url = redis_url
        self.queue_name = queue_name
        self.lock_ttl_seconds = lock_ttl_seconds
        self.poll_seconds = poll_seconds
        self._redis: Any | None = None

    @property
    def heartbeat_key(self) -> str:
        return f"{self.queue_name}:worker-heartbeat"

    async def initialize(self) -> None:
        from redis.asyncio import Redis

        self._redis = Redis.from_url(
            self.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=max(5, int(self.poll_seconds) + 2),
        )
        await self._redis.ping()

    async def enqueue(self, operation_id: UUID) -> None:
        if self._redis is None:
            raise RuntimeError("Redis operation queue is not initialized")
        marker = f"{self.queue_name}:queued:{operation_id}"
        created = await self._redis.set(marker, "1", nx=True, ex=86_400)
        if created:
            await self._redis.lpush(self.queue_name, str(operation_id))

    async def dequeue(self) -> UUID | None:
        if self._redis is None:
            raise RuntimeError("Redis operation queue is not initialized")
        item = await self._redis.brpop(self.queue_name, timeout=max(1, int(self.poll_seconds)))
        if not item:
            return None
        _, raw = item
        try:
            operation_id = UUID(str(raw))
        except ValueError:
            return None
        # The list item is now owned by a worker. Clear the de-duplication marker so a
        # queued operation can be recovered and re-enqueued if the worker exits before execution.
        await self._redis.delete(f"{self.queue_name}:queued:{operation_id}")
        return operation_id

    async def acquire_lock(self, operation_id: UUID, worker_id: str) -> bool:
        if self._redis is None:
            return False
        return bool(
            await self._redis.set(
                f"{self.queue_name}:lock:{operation_id}",
                worker_id,
                nx=True,
                ex=self.lock_ttl_seconds,
            )
        )

    async def refresh_lock(self, operation_id: UUID, worker_id: str) -> None:
        if self._redis is None:
            return
        key = f"{self.queue_name}:lock:{operation_id}"
        current = await self._redis.get(key)
        if current == worker_id:
            await self._redis.expire(key, self.lock_ttl_seconds)

    async def release_lock(self, operation_id: UUID, worker_id: str) -> None:
        if self._redis is None:
            return
        lock_key = f"{self.queue_name}:lock:{operation_id}"
        queued_key = f"{self.queue_name}:queued:{operation_id}"
        current = await self._redis.get(lock_key)
        pipe = self._redis.pipeline(transaction=True)
        if current == worker_id:
            pipe.delete(lock_key)
        pipe.delete(queued_key)
        await pipe.execute()

    async def heartbeat(self, worker_id: str, metadata: dict[str, Any]) -> None:
        if self._redis is None:
            return
        await self._redis.set(
            self.heartbeat_key,
            json.dumps({"worker_id": worker_id, **metadata}, separators=(",", ":")),
            ex=max(60, min(300, self.lock_ttl_seconds // 3)),
        )

    async def depth(self) -> int:
        if self._redis is None:
            return 0
        return int(await self._redis.llen(self.queue_name))

    async def worker_status(self) -> dict[str, Any] | None:
        if self._redis is None:
            return None
        raw, depth = await self._redis.get(self.heartbeat_key), await self.depth()
        if not raw:
            return None
        try:
            value = json.loads(raw)
            if not isinstance(value, dict):
                return None
            return {**value, "queue_depth": int(depth)}
        except json.JSONDecodeError:
            return None

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
