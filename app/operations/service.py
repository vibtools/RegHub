import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import String, cast, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.enums import OperationStatus, TemplateStatus
from app.core.exceptions import DuplicateTemplateError, NotFoundError, ValidationError
from app.models.admin_operation import AdminOperation, OperationLog
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


class OperationService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create(
        self,
        *,
        operation_type: str,
        title: str,
        requested_by: str | None,
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

    async def clone_for_retry(self, operation_id: UUID, requested_by: str | None) -> AdminOperation:
        original = await self.get(operation_id)
        if original.status not in {OperationStatus.FAILED, OperationStatus.CANCELLED}:
            raise ValidationError("Only failed or cancelled operations can be retried")
        return await self.create(
            operation_type=original.operation_type,
            title=f"Retry: {original.title}"[:240],
            requested_by=requested_by,
            input_payload=original.input_payload,
            return_url=original.return_url,
            retry_of_id=original.id,
        )

    async def recover(self) -> list[UUID]:
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
            for item in rows:
                if item.status == OperationStatus.RUNNING:
                    item.status = OperationStatus.FAILED
                    item.error_message = "Operation was interrupted by an application restart"
                    item.completed_at = now
                else:
                    queued.append(item.id)
            await session.commit()
        return queued


class OperationRunner:
    def __init__(self, service: OperationService) -> None:
        self.service = service
        self._container: ApplicationContainer | None = None
        self._tasks: dict[UUID, asyncio.Task[None]] = {}
        self._shutting_down = False

    def bind(self, container: "ApplicationContainer") -> None:
        self._container = container

    async def initialize(self) -> None:
        for operation_id in await self.service.recover():
            self.enqueue(operation_id)

    def enqueue(self, operation_id: UUID) -> None:
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

    async def _log(
        self,
        operation_id: UUID,
        progress: int,
        message: str,
        level: str = "info",
        data: dict[str, Any] | None = None,
    ) -> None:
        await self.service.append_log(
            operation_id, message, level=level, data=data, progress=progress
        )

    async def _execute(self, operation_id: UUID) -> None:
        try:
            if self._container is None:
                raise RuntimeError("Operation runner is not bound to the application container")
            operation = await self.service.get(operation_id)
            await self.service.mark_running(operation_id)
            await self._log(operation_id, 2, f"Starting {operation.title}")
            result = await self._dispatch(operation)
            await self.service.complete(operation_id, result)
        except DuplicateTemplateError as exc:
            await self.service.skip(
                operation_id,
                "No import was required: this repository is already registered in RegHub.",
                {
                    "outcome": "already_exists",
                    "template_id": str(exc.template_id),
                    "template_slug": exc.template_slug,
                    "template_name": exc.template_name,
                    "template_url": f"/admin/template/details/{exc.template_id}",
                },
            )
        except asyncio.CancelledError:
            if self._shutting_down:
                await self.service.fail(
                    operation_id, "Operation interrupted by application shutdown"
                )
            else:
                await self.service.cancel(operation_id)
        except Exception as exc:
            logger.exception("Admin operation %s failed", operation_id)
            await self.service.append_log(
                operation_id,
                f"{exc.__class__.__name__}: {exc}",
                level="error",
                data={"exception_type": exc.__class__.__name__},
            )
            await self.service.fail(operation_id, str(exc))

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
        await self._log(operation.id, 10, f"Validating {adapter.title()} repository URL")
        await self._log(operation.id, 20, f"Connecting to {adapter.title()} API")

        async def progress(value: int, message: str, level: str = "info") -> None:
            await self._log(operation.id, value, message, level)

        template = await self._container.template_import_service.import_repository(
            repository_url=str(payload.get("repository_url", "")),
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
        total = len(identifiers)
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
                    await self._log(operation.id, scaled, message, level)

                template = await self._container.template_sync_service.sync_one(
                    identifier,
                    requested_by=operation.requested_by,
                    progress=progress,
                )
                synced += 1
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
        return {"synced": synced, "failed": len(errors), "errors": errors}

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
