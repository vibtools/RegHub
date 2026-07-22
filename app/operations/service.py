import asyncio
import json
import logging
import re
import time
import traceback
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import String, cast, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.enums import OperationStatus, TemplateStatus
from app.core.exceptions import DuplicateTemplateError, NotFoundError, ValidationError
from app.models.admin_operation import AdminOperation, OperationLog
from app.operations.queue import RedisOperationQueue
from app.registry.local import repository_from_manifest, repository_from_zip
from app.registry.template import TemplateService

if TYPE_CHECKING:
    from app.container import ApplicationContainer

logger = logging.getLogger(__name__)
_TERMINAL = {
    OperationStatus.SUCCEEDED,
    OperationStatus.FAILED,
    OperationStatus.CANCELLED,
    OperationStatus.SKIPPED,
}
_SENSITIVE_KEYS = {"secret", "token", "password", "api_key", "authorization", "credential"}
_SECRET_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+\-/=]+"),
    re.compile(r"(?i)(vt_reg_)[A-Za-z0-9_-]+"),
    re.compile(r"(?i)(github_pat_)[A-Za-z0-9_]+"),
    re.compile(r"(?i)(ghp_)[A-Za-z0-9]+"),
)


def _redact_text(value: str) -> str:
    result = value
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]", result)
    return result


def _safe_payload(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return "[MAX_DEPTH]"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in list(value.items())[:100]:
            normalized = str(key).casefold()
            if any(part in normalized for part in _SENSITIVE_KEYS):
                result[str(key)] = "[REDACTED]"
            else:
                result[str(key)] = _safe_payload(item, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple, set)):
        return [_safe_payload(item, depth=depth + 1) for item in list(value)[:100]]
    if isinstance(value, str):
        return _redact_text(value[:4000])
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _redact_text(str(value)[:4000])


def _compact_json(value: Any) -> str:
    return json.dumps(_safe_payload(value), ensure_ascii=False, separators=(",", ":"), default=str)


class OperationService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create(
        self,
        *,
        operation_type: str,
        title: str,
        requested_by: str | None,
        requested_roles: list[str] | tuple[str, ...] | None = None,
        input_payload: dict[str, Any] | None = None,
        return_url: str | None = None,
        retry_of_id: UUID | None = None,
    ) -> AdminOperation:
        async with self._session_factory() as session:
            operation = AdminOperation(
                operation_type=operation_type,
                title=title[:240],
                status=OperationStatus.QUEUED,
                progress=0,
                requested_by=requested_by,
                requested_roles=[str(item)[:80] for item in list(requested_roles or [])[:50]],
                input_payload=input_payload or {},
                return_url=return_url,
                retry_of_id=retry_of_id,
            )
            session.add(operation)
            await session.flush()
            session.add(
                OperationLog(
                    operation=operation,
                    sequence=1,
                    level="info",
                    message="Operation queued",
                    data={"operation_type": operation_type},
                    created_at=datetime.now(UTC),
                )
            )
            await session.commit()
            await session.refresh(operation)
            return operation

    async def get(self, operation_id: UUID, *, with_logs: bool = False) -> AdminOperation:
        async with self._session_factory() as session:
            query = select(AdminOperation).where(AdminOperation.id == operation_id)
            if with_logs:
                query = query.options(selectinload(AdminOperation.logs))
            operation = await session.scalar(query)
            if operation is None:
                raise NotFoundError("Operation not found")
            return operation

    async def list_recent(
        self,
        limit: int = 100,
        *,
        search: str | None = None,
        status: str | None = None,
        operation_type: str | None = None,
        order: str = "desc",
    ) -> list[AdminOperation]:
        query = select(AdminOperation)
        if search and search.strip():
            term = f"%{search.strip()}%"
            query = query.where(
                or_(
                    AdminOperation.title.ilike(term),
                    AdminOperation.operation_type.ilike(term),
                    cast(AdminOperation.id, String).ilike(term),
                    AdminOperation.requested_by.ilike(term),
                )
            )
        if status and status in {item.value for item in OperationStatus}:
            query = query.where(AdminOperation.status == OperationStatus(status))
        if operation_type and operation_type.strip():
            query = query.where(AdminOperation.operation_type == operation_type.strip())
        ordering = (
            AdminOperation.created_at.asc() if order == "asc" else AdminOperation.created_at.desc()
        )
        async with self._session_factory() as session:
            return list(
                (
                    await session.scalars(query.order_by(ordering).limit(max(1, min(limit, 500))))
                ).all()
            )

    async def operation_types(self) -> list[str]:
        async with self._session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(AdminOperation.operation_type)
                        .distinct()
                        .order_by(AdminOperation.operation_type)
                    )
                ).all()
            )

    async def clear_terminal(self, scope: str = "all_terminal") -> int:
        allowed = {
            "all_terminal": list(_TERMINAL),
            "succeeded": [OperationStatus.SUCCEEDED],
            "failed": [OperationStatus.FAILED],
            "cancelled": [OperationStatus.CANCELLED],
            "skipped": [OperationStatus.SKIPPED],
        }
        statuses = allowed.get(scope)
        if statuses is None:
            raise ValidationError("Unsupported operation clear scope")
        async with self._session_factory() as session:
            result = await session.execute(
                delete(AdminOperation).where(AdminOperation.status.in_(statuses))
            )
            await session.commit()
            return int(result.rowcount or 0)

    async def logs_since(self, operation_id: UUID, sequence: int = 0) -> list[OperationLog]:
        async with self._session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(OperationLog)
                        .where(
                            OperationLog.operation_id == operation_id,
                            OperationLog.sequence > sequence,
                        )
                        .order_by(OperationLog.sequence)
                    )
                ).all()
            )

    async def append_log(
        self,
        operation_id: UUID,
        message: str,
        *,
        level: str = "info",
        data: dict[str, Any] | None = None,
        progress: int | None = None,
    ) -> None:
        async with self._session_factory() as session:
            operation = await session.get(AdminOperation, operation_id)
            if operation is None:
                return
            current = int(
                await session.scalar(
                    select(func.max(OperationLog.sequence)).where(
                        OperationLog.operation_id == operation_id
                    )
                )
                or 0
            )
            session.add(
                OperationLog(
                    operation_id=operation_id,
                    sequence=current + 1,
                    level=level[:20],
                    message=message[:10_000],
                    data=data,
                    created_at=datetime.now(UTC),
                )
            )
            if progress is not None:
                operation.progress = max(operation.progress, max(0, min(progress, 100)))
            await session.commit()

    async def mark_running(self, operation_id: UUID) -> None:
        async with self._session_factory() as session:
            operation = await session.get(AdminOperation, operation_id)
            if operation is None:
                raise NotFoundError("Operation not found")
            operation.status = OperationStatus.RUNNING
            operation.progress = max(operation.progress, 1)
            operation.started_at = datetime.now(UTC)
            await session.commit()

    async def complete(self, operation_id: UUID, result: dict[str, Any] | None = None) -> None:
        async with self._session_factory() as session:
            operation = await session.get(AdminOperation, operation_id)
            if operation is None:
                return
            operation.status = OperationStatus.SUCCEEDED
            operation.progress = 100
            operation.result_payload = result or {}
            operation.error_message = None
            operation.completed_at = datetime.now(UTC)
            await session.commit()
        await self.append_log(operation_id, "Operation completed successfully", progress=100)

    async def skip(self, operation_id: UUID, message: str, result: dict[str, Any]) -> None:
        safe = message.strip()[:4000] or "Operation skipped"
        async with self._session_factory() as session:
            operation = await session.get(AdminOperation, operation_id)
            if operation is None:
                return
            operation.status = OperationStatus.SKIPPED
            operation.progress = 100
            operation.result_payload = result
            operation.error_message = None
            operation.completed_at = datetime.now(UTC)
            await session.commit()
        await self.append_log(
            operation_id,
            safe,
            level="notice",
            data={"outcome": "already_exists", **result},
            progress=100,
        )

    async def fail(self, operation_id: UUID, message: str) -> None:
        safe = message.strip()[:4000] or "Operation failed"
        async with self._session_factory() as session:
            operation = await session.get(AdminOperation, operation_id)
            if operation is None:
                return
            operation.status = OperationStatus.FAILED
            operation.error_message = safe
            operation.completed_at = datetime.now(UTC)
            await session.commit()
        await self.append_log(operation_id, safe, level="error")

    async def cancel(self, operation_id: UUID, message: str = "Operation cancelled") -> None:
        async with self._session_factory() as session:
            operation = await session.get(AdminOperation, operation_id)
            if operation is None:
                return
            operation.status = OperationStatus.CANCELLED
            operation.cancel_requested = True
            operation.error_message = message[:4000]
            operation.completed_at = datetime.now(UTC)
            await session.commit()
        await self.append_log(operation_id, message, level="warning")

    async def request_cancel(self, operation_id: UUID) -> None:
        async with self._session_factory() as session:
            operation = await session.get(AdminOperation, operation_id)
            if operation is None:
                raise NotFoundError("Operation not found")
            if operation.status in _TERMINAL:
                return
            operation.cancel_requested = True
            await session.commit()

    async def clone_for_retry(
        self,
        operation_id: UUID,
        requested_by: str | None,
        *,
        requested_roles: list[str] | tuple[str, ...] | None = None,
    ) -> AdminOperation:
        original = await self.get(operation_id)
        if original.status not in {OperationStatus.FAILED, OperationStatus.CANCELLED}:
            raise ValidationError("Only failed or cancelled operations can be retried")
        return await self.create(
            operation_type=original.operation_type,
            title=f"Retry: {original.title}"[:240],
            requested_by=requested_by,
            requested_roles=list(requested_roles or original.requested_roles or []),
            input_payload=original.input_payload,
            return_url=original.return_url,
            retry_of_id=original.id,
        )

    async def recover(self, *, stale_after_seconds: int = 0) -> list[UUID]:
        queued: list[UUID] = []
        async with self._session_factory() as session:
            rows = list(
                (
                    await session.scalars(
                        select(AdminOperation).where(
                            AdminOperation.status.in_(
                                [OperationStatus.QUEUED, OperationStatus.RUNNING]
                            )
                        )
                    )
                ).all()
            )
            now = datetime.now(UTC)
            stale_before = now - timedelta(seconds=max(0, stale_after_seconds))
            for item in rows:
                if item.status == OperationStatus.QUEUED:
                    queued.append(item.id)
                    continue
                started = item.started_at
                if started is not None and started.tzinfo is None:
                    started = started.replace(tzinfo=UTC)
                if stale_after_seconds <= 0 or started is None or started <= stale_before:
                    item.status = OperationStatus.FAILED
                    item.error_message = "Operation was interrupted by a worker restart"
                    item.completed_at = now
            await session.commit()
        return queued

    async def cancel_requested(self, operation_id: UUID) -> bool:
        async with self._session_factory() as session:
            value = await session.scalar(
                select(AdminOperation.cancel_requested).where(AdminOperation.id == operation_id)
            )
            return bool(value)


class OperationCancellationRequested(Exception):
    pass


class OperationRunner:
    def __init__(
        self,
        service: OperationService,
        *,
        backend: str = "inprocess",
        redis_url: str | None = None,
        queue_name: str = "reghub:operations",
        lock_ttl_seconds: int = 900,
        poll_seconds: float = 1.0,
    ) -> None:
        self.service = service
        # ``backend`` remains the deployment-time compatibility default. The effective
        # backend is controlled by the runtime ``redis_worker`` feature flag. This lets
        # an operator provision Redis and a standby worker once, then switch durable
        # processing on or off from Settings without replacing the web application.
        self.backend = backend
        self._container: ApplicationContainer | None = None
        self._tasks: dict[UUID, asyncio.Task[None]] = {}
        self._shutting_down = False
        self._worker_process = False
        self._worker_id = f"worker-{uuid4()}"
        self._redis_worker_enabled = backend == "redis"
        self._queue_initialized = False
        self._queue = (
            RedisOperationQueue(
                redis_url,
                queue_name=queue_name,
                lock_ttl_seconds=lock_ttl_seconds,
                poll_seconds=poll_seconds,
            )
            if redis_url
            else None
        )
        self.lock_ttl_seconds = lock_ttl_seconds

    def bind(self, container: "ApplicationContainer") -> None:
        self._container = container

    @property
    def redis_configured(self) -> bool:
        return self._queue is not None

    @property
    def redis_worker_enabled(self) -> bool:
        return self._redis_worker_enabled

    @property
    def effective_backend(self) -> str:
        return "redis" if self._redis_worker_enabled and self._queue_initialized else "inprocess"

    async def _ensure_queue(self) -> None:
        if self._queue is None:
            raise ValidationError(
                "Redis worker is not configured. Set REDIS_URL and deploy the "
                "standalone worker first."
            )
        if not self._queue_initialized:
            try:
                await self._queue.initialize()
            except Exception as exc:
                raise ValidationError(
                    f"Redis worker connection failed: {exc.__class__.__name__}: {exc}"
                ) from exc
            self._queue_initialized = True

    async def validate_redis_worker_activation(self) -> dict[str, Any]:
        await self._ensure_queue()
        assert self._queue is not None
        status = await self._queue.worker_status()
        if not status:
            raise ValidationError(
                "Redis is reachable, but no standalone RegHub worker heartbeat was found. "
                "Start the worker service before enabling this switch."
            )
        return status

    async def set_redis_worker_enabled(
        self, enabled: bool, *, verify_worker: bool = False
    ) -> None:
        if enabled:
            if verify_worker:
                await self.validate_redis_worker_activation()
            else:
                await self._ensure_queue()
        self._redis_worker_enabled = bool(enabled)

    async def initialize(
        self, *, worker_process: bool = False, redis_worker_enabled: bool | None = None
    ) -> None:
        self._worker_process = worker_process
        if redis_worker_enabled is not None:
            self._redis_worker_enabled = bool(redis_worker_enabled)
        if worker_process:
            await self._ensure_queue()
            if self._redis_worker_enabled:
                assert self._queue is not None
                for operation_id in await self.service.recover(
                    stale_after_seconds=self.lock_ttl_seconds
                ):
                    await self._queue.enqueue(operation_id)
            return
        if self._redis_worker_enabled:
            await self._ensure_queue()
            return
        for operation_id in await self.service.recover():
            await self.enqueue(operation_id)

    async def enqueue(self, operation_id: UUID) -> None:
        if self._redis_worker_enabled:
            await self._ensure_queue()
            assert self._queue is not None
            await self._queue.enqueue(operation_id)
            return
        task = self._tasks.get(operation_id)
        if task and not task.done():
            return
        task = asyncio.create_task(
            self._execute(operation_id), name=f"reghub-operation-{operation_id}"
        )
        self._tasks[operation_id] = task
        task.add_done_callback(lambda _task, oid=operation_id: self._tasks.pop(oid, None))

    async def request_cancel(self, operation_id: UUID) -> None:
        await self.service.request_cancel(operation_id)
        task = self._tasks.get(operation_id)
        if task and not task.done():
            task.cancel()

    async def shutdown(self) -> None:
        self._shutting_down = True
        tasks = [task for task in self._tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        if self._queue is not None and self._queue_initialized:
            await self._queue.close()
            self._queue_initialized = False

    async def worker_status(self) -> dict[str, Any] | None:
        if not self._redis_worker_enabled:
            return {
                "backend": "inprocess",
                "worker": "web-process",
                "queue_depth": 0,
                "redis_configured": self.redis_configured,
                "redis_worker_enabled": False,
            }
        if self._queue is None or not self._queue_initialized:
            return None
        try:
            value = await self._queue.worker_status()
            return (
                {**value, "redis_worker_enabled": True, "redis_configured": True}
                if value
                else None
            )
        except Exception:
            logger.exception("Unable to read Redis operation worker status")
            return None

    async def _audit_terminal(
        self,
        operation: AdminOperation | None,
        *,
        outcome: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        if self._container is None or operation is None:
            return

        # Governance and cache services are mandatory in the full ApplicationContainer, but
        # operation runners are also exercised by isolated adapters/tests and may be embedded
        # in reduced maintenance contexts. A missing or temporarily unavailable side-effect
        # service must never rewrite an already-persisted successful operation as failed.
        audit = getattr(self._container, "audit", None)
        if audit is not None:
            try:
                await audit.append(
                    action=f"operation.{operation.operation_type}",
                    resource_type="admin_operation",
                    resource_id=str(operation.id),
                    outcome=outcome,
                    actor_subject=operation.requested_by,
                    actor_roles=list(operation.requested_roles or []),
                    details={
                        "title": operation.title,
                        "result": _safe_payload(result or {}),
                        "error": _redact_text(error or "") or None,
                    },
                )
            except Exception:
                logger.exception("Unable to append terminal audit event for %s", operation.id)
                try:
                    await self.service.append_log(
                        operation.id,
                        "Governance audit append failed after operation completion",
                        level="warning",
                        data={"outcome": outcome},
                    )
                except Exception:
                    logger.exception("Unable to persist the audit-degradation operation warning")
        else:
            logger.debug("Audit service is unavailable for operation %s", operation.id)

        if operation.operation_type in {
            "import_repository",
            "import_local_manifest",
            "import_local_zip",
            "sync_templates",
            "set_template_status",
            "generate_thumbnails",
            "retry_screenshot_jobs",
        }:
            cache = getattr(self._container, "catalog_cache", None)
            if cache is None:
                logger.debug("Catalog cache is unavailable for operation %s", operation.id)
                return
            try:
                await cache.invalidate_all()
            except Exception:
                logger.exception("Unable to invalidate catalog cache after %s", operation.id)
                try:
                    await self.service.append_log(
                        operation.id,
                        "Catalog cache invalidation failed; database result remains authoritative",
                        level="warning",
                        data={"outcome": outcome},
                    )
                except Exception:
                    logger.exception("Unable to persist the cache-degradation operation warning")

    async def run_forever(self) -> None:
        if self._queue is None:
            raise RuntimeError("The standalone worker requires REDIS_URL")
        await self._ensure_queue()
        next_reconcile = 0.0
        next_feature_refresh = 0.0
        while not self._shutting_down:
            now = time.monotonic()
            if now >= next_feature_refresh and self._container is not None:
                await self._container.runtime_settings.reload()
                self._redis_worker_enabled = self._container.feature_enabled("redis_worker")
                next_feature_refresh = now + 5.0
            if not self._redis_worker_enabled:
                queued_depth = await self._queue.depth()
                if queued_depth <= 0:
                    await self._queue.heartbeat(
                        self._worker_id,
                        {
                            "backend": "redis",
                            "status": "standby",
                            "runtime_enabled": False,
                            "queue_depth": 0,
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                    )
                    await asyncio.sleep(max(0.5, self._queue.poll_seconds))
                    continue
                # Disabling the switch routes all *new* operations back to the web
                # process. Already queued durable jobs are drained so no administrator
                # action is stranded in QUEUED state.
                await self._queue.heartbeat(
                    self._worker_id,
                    {
                        "backend": "redis",
                        "status": "draining",
                        "runtime_enabled": False,
                        "queue_depth": queued_depth,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )
            if self._redis_worker_enabled and now >= next_reconcile:
                for queued_id in await self.service.recover(
                    stale_after_seconds=self.lock_ttl_seconds
                ):
                    await self._queue.enqueue(queued_id)
                next_reconcile = now + 60.0
            await self._queue.heartbeat(
                self._worker_id,
                {
                    "backend": "redis",
                    "status": "idle" if self._redis_worker_enabled else "draining",
                    "runtime_enabled": self._redis_worker_enabled,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
            operation_id = await self._queue.dequeue()
            if operation_id is None:
                continue
            if not await self._queue.acquire_lock(operation_id, self._worker_id):
                await asyncio.sleep(min(1.0, self._queue.poll_seconds))
                await self._queue.enqueue(operation_id)
                continue
            await self._queue.heartbeat(
                self._worker_id,
                {
                    "backend": "redis",
                    "status": "running",
                    "operation_id": str(operation_id),
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
            try:
                await self._execute(operation_id)
            finally:
                await self._queue.release_lock(operation_id, self._worker_id)

    async def _log(
        self,
        operation_id: UUID,
        progress: int,
        message: str,
        level: str = "info",
        data: dict[str, Any] | None = None,
    ) -> None:
        if await self.service.cancel_requested(operation_id):
            raise OperationCancellationRequested
        await self.service.append_log(
            operation_id, message, level=level, data=data, progress=progress
        )
        if self._worker_process and self._queue is not None and self._queue_initialized:
            await self._queue.refresh_lock(operation_id, self._worker_id)
            await self._queue.heartbeat(
                self._worker_id,
                {
                    "backend": "redis",
                    "status": "running",
                    "operation_id": str(operation_id),
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )

    async def _execute(self, operation_id: UUID) -> None:
        started = time.perf_counter()
        stage = "bootstrap"
        operation: AdminOperation | None = None
        try:
            if self._container is None:
                raise RuntimeError("Operation runner is not bound to the application container")
            if self._worker_process:
                # Runtime Settings are controlled by the web process but stored in PostgreSQL.
                # Refresh integrations and feature gates at every durable job boundary so a
                # standalone Redis worker applies Settings changes without a redeploy/restart.
                await self._container.reload_runtime(preserve_inflight=False)
            operation = await self.service.get(operation_id)
            if operation.status in _TERMINAL:
                return
            await self.service.mark_running(operation_id)
            await self._log(
                operation_id,
                1,
                f"$ reghub operation run --id {operation.id} --type {operation.operation_type}",
                "notice",
            )
            await self._log(
                operation_id,
                2,
                "Operation context initialized",
                "debug",
                {
                    "requested_by": operation.requested_by or "system",
                    "return_url": operation.return_url,
                    "retry_of_id": str(operation.retry_of_id) if operation.retry_of_id else None,
                },
            )
            await self._log(
                operation_id,
                3,
                "Input payload accepted",
                "debug",
                {"payload": _safe_payload(operation.input_payload or {})},
            )
            stage = "dispatch"
            await self._log(
                operation_id,
                4,
                f"Dispatching handler for {operation.operation_type}",
                "debug",
            )
            result = await self._dispatch(operation)
            stage = "finalize"
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            await self._log(
                operation_id,
                98,
                "Handler completed; finalizing persistent operation state",
                "debug",
                {"elapsed_ms": elapsed_ms, "result": _safe_payload(result)},
            )
            await self.service.complete(operation_id, result)
            await self._audit_terminal(operation, outcome="succeeded", result=result)
        except DuplicateTemplateError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            await self._log(
                operation_id,
                100,
                "Repository lookup matched an existing registry template; import changed to no-op",
                "notice",
                {
                    "elapsed_ms": elapsed_ms,
                    "template_id": str(exc.template_id),
                    "template_slug": exc.template_slug,
                },
            )
            skipped_result = {
                "outcome": "already_exists",
                "template_id": str(exc.template_id),
                "template_slug": exc.template_slug,
                "template_name": exc.template_name,
                "template_url": f"/admin/template/details/{exc.template_id}",
            }
            await self.service.skip(
                operation_id,
                "No import was required: this repository is already registered in RegHub.",
                skipped_result,
            )
            await self._audit_terminal(operation, outcome="skipped", result=skipped_result)
        except OperationCancellationRequested:
            await self.service.cancel(operation_id, "Operation cancelled by administrator")
            await self._audit_terminal(operation, outcome="cancelled")
        except asyncio.CancelledError:
            if self._shutting_down:
                await self.service.fail(
                    operation_id, "Operation interrupted by application shutdown"
                )
            else:
                await self.service.cancel(operation_id)
            await self._audit_terminal(operation, outcome="cancelled")
        except Exception as exc:
            logger.exception("Admin operation %s failed", operation_id)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            trace = _redact_text(traceback.format_exc(limit=16))[-12000:]
            await self.service.append_log(
                operation_id,
                f"FAILED stage={stage}: {exc.__class__.__name__}: {_redact_text(str(exc))}",
                level="error",
                data={
                    "stage": stage,
                    "exception_type": exc.__class__.__name__,
                    "elapsed_ms": elapsed_ms,
                    "traceback": trace,
                },
            )
            await self.service.fail(operation_id, _redact_text(str(exc)))
            await self._audit_terminal(
                operation,
                outcome="failed",
                error=f"{exc.__class__.__name__}: {_redact_text(str(exc))}",
            )

    async def _dispatch(self, operation: AdminOperation) -> dict[str, Any]:
        handlers = {
            "import_repository": self._import_repository,
            "import_local_manifest": self._import_local_manifest,
            "import_local_zip": self._import_local_zip,
            "sync_templates": self._sync_templates,
            "set_template_status": self._set_template_status,
            "generate_thumbnails": self._generate_thumbnails,
            "retry_screenshot_jobs": self._retry_screenshot_jobs,
        }
        handler = handlers.get(operation.operation_type)
        if handler is None:
            raise ValidationError(f"Unsupported operation type: {operation.operation_type}")
        return await handler(operation)

    async def _import_repository(self, operation: AdminOperation) -> dict[str, Any]:
        assert self._container is not None
        payload = operation.input_payload
        adapter = str(payload.get("adapter", "github"))
        feature = f"{adapter}_import"
        self._container.require_feature(feature, task=True)
        repository_url = str(payload.get("repository_url", ""))
        await self._log(operation.id, 7, f"Feature gate accepted: {feature}", "debug")
        await self._log(
            operation.id,
            8,
            "Import parameters resolved",
            "debug",
            {
                "adapter": adapter,
                "repository_url": repository_url,
                "category_id": payload.get("category_id"),
                "provider_id": payload.get("provider_id"),
            },
        )
        await self._log(operation.id, 10, f"Validating {adapter.title()} repository URL")
        await self._log(operation.id, 20, f"Connecting to {adapter.title()} API")

        async def progress(value: int, message: str, level: str = "info") -> None:
            await self._log(operation.id, value, _redact_text(message), level)

        template = await self._container.template_import_service.import_repository(
            repository_url=repository_url,
            requested_by=operation.requested_by or "system",
            adapter_name=adapter,
            category_id=UUID(str(payload["category_id"])) if payload.get("category_id") else None,
            provider_id=UUID(str(payload["provider_id"])) if payload.get("provider_id") else None,
            progress=progress,
        )
        await self._log(operation.id, 95, f"Draft template created: {template.name}")
        return {
            "template_id": str(template.id),
            "template_slug": template.slug,
            "template_name": template.name,
            "status": template.status.value,
        }

    async def _import_local_manifest(self, operation: AdminOperation) -> dict[str, Any]:
        assert self._container is not None
        self._container.require_feature("local_import", task=True)
        payload = operation.input_payload
        await self._log(operation.id, 10, "Validating local manifest")
        imported = repository_from_manifest(payload.get("manifest") or {})
        await self._log(operation.id, 30, "Manifest validated; starting deterministic analysis")

        async def progress(value: int, message: str, level: str = "info") -> None:
            await self._log(operation.id, value, message, level)

        template = await self._container.template_import_service.import_imported_repository(
            imported=imported,
            requested_by=operation.requested_by or "system",
            category_id=UUID(str(payload["category_id"])) if payload.get("category_id") else None,
            provider_id=UUID(str(payload["provider_id"])) if payload.get("provider_id") else None,
            progress=progress,
        )
        return {"template_id": str(template.id), "template_slug": template.slug}

    async def _import_local_zip(self, operation: AdminOperation) -> dict[str, Any]:
        assert self._container is not None
        self._container.require_feature("local_import", task=True)
        payload = operation.input_payload
        path = Path(str(payload.get("temporary_path", "")))
        if not await asyncio.to_thread(path.is_file):
            raise ValidationError("Temporary ZIP file is unavailable; submit the import again")
        try:
            await self._log(operation.id, 10, "Reading temporary ZIP upload")
            data = await asyncio.to_thread(path.read_bytes)
            await self._log(operation.id, 20, "Inspecting ZIP safety limits and metadata")
            imported = repository_from_zip(
                data,
                str(payload.get("filename", path.name)),
                max_uncompressed_bytes=self._container.local_upload_max_uncompressed_bytes,
                max_entries=self._container.local_upload_max_entries,
            )

            async def progress(value: int, message: str, level: str = "info") -> None:
                await self._log(operation.id, value, message, level)

            template = await self._container.template_import_service.import_imported_repository(
                imported=imported,
                requested_by=operation.requested_by or "system",
                category_id=(
                    UUID(str(payload["category_id"])) if payload.get("category_id") else None
                ),
                provider_id=(
                    UUID(str(payload["provider_id"])) if payload.get("provider_id") else None
                ),
                progress=progress,
            )
            return {"template_id": str(template.id), "template_slug": template.slug}
        finally:
            await asyncio.to_thread(path.unlink, missing_ok=True)

    async def _sync_templates(self, operation: AdminOperation) -> dict[str, Any]:
        assert self._container is not None
        self._container.require_feature("source_sync", task=True)
        identifiers = [
            UUID(str(value)) for value in operation.input_payload.get("template_ids", [])
        ]
        if not identifiers:
            raise ValidationError("No templates were selected")
        errors: list[str] = []
        synced = 0
        synced_template: Any | None = None
        total = len(identifiers)
        await self._log(
            operation.id,
            5,
            "Sync batch prepared",
            "debug",
            {"template_count": total, "template_ids": [str(item) for item in identifiers]},
        )
        for index, identifier in enumerate(identifiers, start=1):
            await self._log(
                operation.id,
                5 + int((index - 1) / total * 85),
                f"Synchronizing template {index} of {total}: {identifier}",
            )
            try:

                async def progress(
                    value: int,
                    message: str,
                    level: str = "info",
                    *,
                    current_index: int = index,
                ) -> None:
                    scaled = 5 + int(((current_index - 1) + value / 100) / total * 85)
                    await self._log(
                        operation.id,
                        scaled,
                        f"[{current_index}/{total}] {_redact_text(message)}",
                        level,
                    )

                template = await self._container.template_sync_service.sync_one(
                    identifier,
                    requested_by=operation.requested_by,
                    progress=progress,
                )
                synced += 1
                synced_template = template
                await self._log(
                    operation.id,
                    5 + int(index / total * 85),
                    f"Synchronized {template.name}",
                )
            except Exception as exc:
                errors.append(f"{identifier}: {exc}")
                await self._log(operation.id, 5 + int(index / total * 85), str(exc), "error")
        if errors and not synced:
            raise ValidationError("; ".join(errors))
        result: dict[str, Any] = {"synced": synced, "failed": len(errors), "errors": errors}
        if total == 1 and synced_template is not None:
            result.update(
                {
                    "template_id": str(synced_template.id),
                    "template_slug": synced_template.slug,
                    "template_name": synced_template.name,
                    "status": synced_template.status.value,
                }
            )
        await self._log(operation.id, 94, "Sync batch result", "debug", result)
        return result

    async def _set_template_status(self, operation: AdminOperation) -> dict[str, Any]:
        assert self._container is not None
        self._container.require_feature("template_publication", task=True)
        payload = operation.input_payload
        identifiers = [UUID(str(value)) for value in payload.get("template_ids", [])]
        status = TemplateStatus(str(payload.get("status", "draft")))
        await self._log(operation.id, 30, f"Validating {len(identifiers)} selected templates")
        async with self._container.session_factory() as session:
            changed = await TemplateService.set_status(session, identifiers, status)
        await self._log(operation.id, 90, f"Updated {changed} template(s) to {status.value}")
        return {"updated": changed, "status": status.value}

    async def _generate_thumbnails(self, operation: AdminOperation) -> dict[str, Any]:
        assert self._container is not None
        self._container.require_feature("screenshot_generation", task=True)
        if not self._container.screenshot_job_service.enabled:
            raise ValidationError("Screenshot service is enabled but not configured")
        identifiers = [
            UUID(str(value)) for value in operation.input_payload.get("template_ids", [])
        ]
        if not identifiers:
            raise ValidationError("No templates were selected")
        generated = 0
        errors: list[str] = []
        total = len(identifiers)
        for index, identifier in enumerate(identifiers, start=1):
            await self._log(
                operation.id,
                10 + int((index - 1) / total * 80),
                f"Generating thumbnail {index} of {total}",
            )
            try:
                job = await self._container.screenshot_job_service.create_and_run(
                    identifier, operation.requested_by
                )
                generated += 1
                await self._log(
                    operation.id,
                    10 + int(index / total * 80),
                    f"Screenshot generated: {job.screenshot_url}",
                )
            except Exception as exc:
                errors.append(f"{identifier}: {exc}")
                await self._log(operation.id, 10 + int(index / total * 80), str(exc), "error")
        if errors and not generated:
            raise ValidationError("; ".join(errors))
        return {"generated": generated, "failed": len(errors), "errors": errors}

    async def _retry_screenshot_jobs(self, operation: AdminOperation) -> dict[str, Any]:
        assert self._container is not None
        self._container.require_feature("screenshot_generation", task=True)
        identifiers = [UUID(str(value)) for value in operation.input_payload.get("job_ids", [])]
        if not identifiers:
            raise ValidationError("No screenshot jobs were selected")
        retried = 0
        errors: list[str] = []
        for index, identifier in enumerate(identifiers, start=1):
            await self._log(
                operation.id,
                10 + index * 70 // max(1, len(identifiers)),
                f"Retrying job {identifier}",
            )
            try:
                await self._container.screenshot_job_service.retry(
                    identifier, operation.requested_by
                )
                retried += 1
            except Exception as exc:
                errors.append(f"{identifier}: {exc}")
                await self._log(
                    operation.id,
                    10 + index * 70 // max(1, len(identifiers)),
                    str(exc),
                    "error",
                )
        if errors and not retried:
            raise ValidationError("; ".join(errors))
        return {"retried": retried, "failed": len(errors), "errors": errors}
