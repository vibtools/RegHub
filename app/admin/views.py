import asyncio
import json
import logging
import secrets
import tempfile
from datetime import UTC, datetime
from hmac import compare_digest
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from sqladmin import BaseView, ModelView, action, expose
from sqladmin.filters import BooleanFilter, ForeignKeyFilter, StaticValuesFilter
from sqlalchemy import or_, select
from starlette.datastructures import URL, UploadFile
from starlette.requests import Request
from starlette.responses import (
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    StreamingResponse,
)

from app.core.enums import (
    ImportStatus,
    OperationStatus,
    ProviderType,
    ScreenshotJobStatus,
    TemplateStatus,
)
from app.core.exceptions import PermissionDeniedError, RegistryError, ValidationError
from app.database.session import async_session_factory
from app.governance.rbac import has_permission, permissions_for_roles, require_permission
from app.models.audit_event import AuditEvent
from app.models.category import Category
from app.models.framework import Framework
from app.models.import_history import ImportHistory
from app.models.provider import Provider
from app.models.screenshot_job import ScreenshotJob
from app.models.sync_history import SyncHistory
from app.models.template import Template
from app.models.template_asset import TemplateAsset
from app.models.template_version import TemplateVersion
from app.registry.media import TemplateAssetService
from app.runtime.api_catalog import endpoint_by_key, endpoint_rows

logger = logging.getLogger(__name__)
_TERMINAL_OPERATION_VALUES = {
    OperationStatus.SUCCEEDED.value,
    OperationStatus.FAILED.value,
    OperationStatus.CANCELLED.value,
    OperationStatus.SKIPPED.value,
}
_OPERATION_PERMISSIONS = {
    "import_repository": "imports.run",
    "import_local_manifest": "imports.run",
    "import_local_zip": "imports.run",
    "sync_templates": "sync.run",
    "set_template_status": "publication.manage",
    "generate_thumbnails": "media.write",
    "retry_screenshot_jobs": "media.write",
}


def _operation_permission(operation_type: str) -> str:
    return _OPERATION_PERMISSIONS.get(operation_type, "operations.run")


_SETTINGS_PANES = {"features-pane", "integrations-pane", "api-manage-pane", "custom-api-pane"}
_SETTINGS_ACTION_PANES = {
    "save_features": "features-pane",
    "save_integration": "integrations-pane",
    "remove_integration": "integrations-pane",
    "reload_runtime": "features-pane",
    "save_api_mode": "api-manage-pane",
    "create_api_token": "api-manage-pane",
    "toggle_api_token": "api-manage-pane",
    "delete_api_token": "api-manage-pane",
    "add_block_rule": "api-manage-pane",
    "update_block_rule": "api-manage-pane",
    "delete_block_rule": "api-manage-pane",
}


def _settings_pane(value: object, action_name: str = "") -> str:
    candidate = str(value or "").strip().removeprefix("#")
    if candidate in _SETTINGS_PANES:
        return candidate
    return _SETTINGS_ACTION_PANES.get(action_name, "features-pane")


def _safe_admin_return_url(request: Request, default: str = "/admin/template/list") -> str:
    candidate = request.query_params.get("return_url") or request.headers.get("referer")
    if not candidate:
        return default
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc:
        if parsed.netloc != request.url.netloc:
            return default
        candidate = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    if not candidate.startswith("/admin") or candidate.startswith("//"):
        return default
    return candidate[:1000]


def _operation_url(operation_id: UUID) -> str:
    return f"/admin/operations/{operation_id}"


def _operation_template_id(operation: object) -> UUID | None:
    result = getattr(operation, "result_payload", None) or {}
    raw_identifier = result.get("template_id") if isinstance(result, dict) else None
    if not raw_identifier:
        return None
    try:
        return UUID(str(raw_identifier))
    except (TypeError, ValueError):
        return None


async def _operation_template_summary(
    container: object, operation: object
) -> dict[str, object] | None:
    template_id = _operation_template_id(operation)
    session_factory = getattr(container, "session_factory", None)
    if template_id is None or session_factory is None:
        return None
    async with session_factory() as session:
        template = await session.get(Template, template_id)
        if template is None:
            return None
        screenshots = list(template.screenshots or [])
        thumbnail_url = template.thumbnail_url or next(
            (item for item in screenshots if isinstance(item, str) and item.startswith("https://")),
            None,
        )
        return {
            "id": str(template.id),
            "name": template.name,
            "slug": template.slug,
            "short_description": template.short_description or template.description or "",
            "thumbnail_url": thumbnail_url,
            "repository_url": template.repository_url,
            "repository_adapter": template.repository_adapter,
            "provider": template.provider.name if template.provider else "Unassigned",
            "category": template.category.name if template.category else "Unassigned",
            "framework": template.framework.name if template.framework else "Unknown",
            "framework_version": template.framework_version,
            "quality_score": template.quality_score,
            "status": template.status.value,
            "details_url": f"/admin/template/details/{template.id}",
        }


def _write_temporary_zip(data: bytes) -> str:
    temp_dir = Path(tempfile.gettempdir()) / "reghub-operations"
    temp_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb", suffix=".zip", prefix="upload-", dir=temp_dir, delete=False
    ) as handle:
        handle.write(data)
        return handle.name


class GovernedModelView(ModelView):
    mutation_permission = "templates.write"

    def is_accessible(self, request: Request) -> bool:
        identity = getattr(request.state, "admin_identity", None)
        return bool(identity and has_permission(identity, "registry.read"))

    async def on_model_change(
        self, data: dict[str, object], model: object, is_created: bool, request: Request
    ) -> None:
        require_permission(request, self.mutation_permission)

    async def after_model_change(
        self, data: dict[str, object], model: object, is_created: bool, request: Request
    ) -> None:
        identity = require_permission(request, self.mutation_permission)
        await request.app.state.container.audit.append(
            action="admin.create" if is_created else "admin.update",
            resource_type=getattr(model, "__tablename__", model.__class__.__name__),
            resource_id=str(getattr(model, "id", "")) or None,
            identity=identity,
            request=request,
            details={"fields": sorted(data)},
        )
        await request.app.state.container.catalog_cache.invalidate_all()

    async def on_model_delete(self, model: object, request: Request) -> None:
        require_permission(request, self.mutation_permission)

    async def after_model_delete(self, model: object, request: Request) -> None:
        identity = require_permission(request, self.mutation_permission)
        await request.app.state.container.audit.append(
            action="admin.delete",
            resource_type=getattr(model, "__tablename__", model.__class__.__name__),
            resource_id=str(getattr(model, "id", "")) or None,
            identity=identity,
            request=request,
        )
        await request.app.state.container.catalog_cache.invalidate_all()


class CategoryAdmin(GovernedModelView, model=Category):
    name = "Category"
    name_plural = "Categories"
    icon = "fa-solid fa-folder-tree"
    column_list = [Category.name, Category.slug, Category.is_active, Category.updated_at]
    column_searchable_list = [Category.name, Category.slug]
    column_sortable_list = [Category.name, Category.created_at, Category.updated_at]
    form_excluded_columns = [Category.templates, Category.created_at, Category.updated_at]


class ProviderAdmin(GovernedModelView, model=Provider):
    icon = "fa-solid fa-building"
    column_list = [Provider.name, Provider.slug, Provider.provider_type, Provider.is_active]
    column_searchable_list = [Provider.name, Provider.slug, Provider.website_url]
    column_sortable_list = [
        Provider.name,
        Provider.provider_type,
        Provider.is_active,
        Provider.created_at,
        Provider.updated_at,
    ]
    column_default_sort = [(Provider.name, False)]
    column_filters = [
        StaticValuesFilter(
            Provider.provider_type,
            [(item.name, item.value.title()) for item in ProviderType],
            title="Provider type",
        ),
        BooleanFilter(Provider.is_active, title="Active"),
    ]
    form_excluded_columns = [Provider.templates, Provider.created_at, Provider.updated_at]


class FrameworkAdmin(GovernedModelView, model=Framework):
    icon = "fa-solid fa-layer-group"
    column_list = [Framework.name, Framework.slug, Framework.is_active, Framework.updated_at]
    column_searchable_list = [Framework.name, Framework.slug, Framework.website_url]
    column_sortable_list = [
        Framework.name,
        Framework.is_active,
        Framework.created_at,
        Framework.updated_at,
    ]
    column_default_sort = [(Framework.name, False)]
    column_filters = [BooleanFilter(Framework.is_active, title="Active")]
    form_excluded_columns = [Framework.templates, Framework.created_at, Framework.updated_at]


class TemplateAdmin(GovernedModelView, model=Template):
    icon = "fa-solid fa-cubes"
    column_list = [
        Template.name,
        Template.status,
        Template.framework,
        Template.framework_version,
        Template.repository_adapter,
        Template.quality_score,
        Template.provider,
        Template.category,
        Template.is_featured,
        Template.updated_at,
    ]
    column_searchable_list = [Template.name, Template.slug, Template.repository_url]
    column_sortable_list = [
        Template.name,
        Template.status,
        Template.quality_score,
        Template.stars_count,
        Template.created_at,
        Template.published_at,
        Template.updated_at,
    ]
    column_default_sort = [(Template.updated_at, True), (Template.name, False)]
    column_filters = [
        StaticValuesFilter(
            Template.status,
            values=[(status.name, status.value.title()) for status in TemplateStatus],
            title="Status",
        ),
        BooleanFilter(Template.is_featured, title="Featured"),
        ForeignKeyFilter(
            Template.framework_id,
            Framework.name,
            foreign_model=Framework,
            title="Framework",
        ),
        ForeignKeyFilter(
            Template.provider_id,
            Provider.name,
            foreign_model=Provider,
            title="Provider",
        ),
        ForeignKeyFilter(
            Template.category_id,
            Category.name,
            foreign_model=Category,
            title="Category",
        ),
    ]
    form_excluded_columns = [
        Template.created_at,
        Template.updated_at,
        Template.status,
        Template.published_at,
        Template.last_synced_at,
        Template.source_updated_at,
        Template.last_analysis_at,
        Template.external_repository_id,
        Template.repository_adapter,
        Template.stars_count,
        Template.forks_count,
        Template.created_by,
        Template.versions,
        Template.sync_history,
        Template.assets,
        Template.screenshot_jobs,
    ]
    can_export = True
    can_view_details = True

    @staticmethod
    def _selected_ids(request: Request) -> list[UUID]:
        raw = request.query_params.get("pks", "")
        try:
            return [UUID(value) for value in raw.split(",") if value]
        except ValueError as exc:
            raise ValidationError("Selected template identifiers are invalid") from exc

    async def _queue(
        self,
        request: Request,
        *,
        operation_type: str,
        title: str,
        payload: dict[str, object],
    ) -> RedirectResponse:
        require_permission(request, _operation_permission(operation_type))
        container = self._admin_ref.app.state.container
        container.require_feature("operations_console", task=True)
        operation = await container.operation_service.create(
            operation_type=operation_type,
            title=title,
            requested_by=request.state.admin_identity.subject,
            requested_roles=list(request.state.admin_identity.roles),
            input_payload=payload,
            return_url=_safe_admin_return_url(request),
        )
        await container.operation_runner.enqueue(operation.id)
        return RedirectResponse(_operation_url(operation.id), status_code=302)

    async def _set_status(self, request: Request, status: TemplateStatus):
        identifiers = self._selected_ids(request)
        if not identifiers:
            return RedirectResponse(
                URL(_safe_admin_return_url(request)).include_query_params(
                    error="No templates were selected"
                ),
                status_code=302,
            )
        return await self._queue(
            request,
            operation_type="set_template_status",
            title=f"Set {len(identifiers)} template(s) to {status.value}",
            payload={"template_ids": [str(value) for value in identifiers], "status": status.value},
        )

    @action("publish", "Publish", "Publish the selected templates?")
    async def publish(self, request: Request):
        return await self._set_status(request, TemplateStatus.PUBLISHED)

    @action("draft", "Move to Draft", "Move the selected templates to draft?")
    async def draft(self, request: Request):
        return await self._set_status(request, TemplateStatus.DRAFT)

    @action("disable", "Disable", "Disable the selected templates?")
    async def disable(self, request: Request):
        return await self._set_status(request, TemplateStatus.DISABLED)

    @action(
        "sync_source", "Sync Source", "Refresh metadata and analysis from the selected sources?"
    )
    async def sync_source(self, request: Request):
        identifiers = self._selected_ids(request)
        if not identifiers:
            return RedirectResponse(
                URL(_safe_admin_return_url(request)).include_query_params(
                    error="No templates were selected"
                ),
                status_code=302,
            )
        return await self._queue(
            request,
            operation_type="sync_templates",
            title=f"Synchronize {len(identifiers)} template source(s)",
            payload={"template_ids": [str(value) for value in identifiers]},
        )

    @action("generate_thumbnail", "Generate Thumbnail", "Generate thumbnails from preview URLs?")
    async def generate_thumbnail(self, request: Request):
        identifiers = self._selected_ids(request)
        if not identifiers:
            return RedirectResponse(
                URL(_safe_admin_return_url(request)).include_query_params(
                    error="No templates were selected"
                ),
                status_code=302,
            )
        if len(identifiers) > 10:
            return RedirectResponse(
                URL(_safe_admin_return_url(request)).include_query_params(
                    error="Generate at most 10 thumbnails at a time"
                ),
                status_code=302,
            )
        return await self._queue(
            request,
            operation_type="generate_thumbnails",
            title=f"Generate {len(identifiers)} template thumbnail(s)",
            payload={"template_ids": [str(value) for value in identifiers]},
        )


class ImportHistoryAdmin(ModelView, model=ImportHistory):
    name_plural = "Import History"
    icon = "fa-solid fa-clock-rotate-left"
    column_searchable_list = [
        ImportHistory.repository_url,
        ImportHistory.adapter,
        ImportHistory.requested_by,
    ]
    column_sortable_list = [
        ImportHistory.status,
        ImportHistory.adapter,
        ImportHistory.created_at,
        ImportHistory.completed_at,
    ]
    column_default_sort = [(ImportHistory.created_at, True)]
    column_filters = [
        StaticValuesFilter(
            ImportHistory.status,
            [(item.name, item.value.title()) for item in ImportStatus],
            title="Status",
        ),
        StaticValuesFilter(
            ImportHistory.adapter,
            [(value, value.title()) for value in ["github", "gitlab", "bitbucket", "local"]],
            title="Adapter",
        ),
    ]
    column_list = [
        ImportHistory.repository_url,
        ImportHistory.adapter,
        ImportHistory.status,
        ImportHistory.requested_by,
        ImportHistory.created_at,
        ImportHistory.completed_at,
    ]
    can_create = False
    can_edit = False
    can_delete = False
    can_view_details = True


class SyncHistoryAdmin(ModelView, model=SyncHistory):
    name_plural = "Sync History"
    icon = "fa-solid fa-arrows-rotate"
    column_searchable_list = [
        SyncHistory.adapter,
        SyncHistory.trigger,
        SyncHistory.requested_by,
        SyncHistory.source_revision,
    ]
    column_sortable_list = [
        SyncHistory.status,
        SyncHistory.adapter,
        SyncHistory.created_at,
        SyncHistory.completed_at,
    ]
    column_default_sort = [(SyncHistory.created_at, True)]
    column_filters = [
        StaticValuesFilter(
            SyncHistory.status,
            [(item.name, item.value.title()) for item in ImportStatus],
            title="Status",
        ),
        StaticValuesFilter(
            SyncHistory.adapter,
            [(value, value.title()) for value in ["github", "gitlab", "bitbucket"]],
            title="Adapter",
        ),
        StaticValuesFilter(
            SyncHistory.trigger,
            [(value, value.title()) for value in ["import", "manual", "scheduled"]],
            title="Trigger",
        ),
    ]
    column_list = [
        SyncHistory.template,
        SyncHistory.adapter,
        SyncHistory.status,
        SyncHistory.trigger,
        SyncHistory.requested_by,
        SyncHistory.source_revision,
        SyncHistory.created_at,
        SyncHistory.completed_at,
    ]
    can_create = False
    can_edit = False
    can_delete = False
    can_view_details = True


class AuditEventAdmin(ModelView, model=AuditEvent):
    name = "Audit Event"
    name_plural = "Audit Trail"
    icon = "fa-solid fa-shield-halved"

    def is_accessible(self, request: Request) -> bool:
        identity = getattr(request.state, "admin_identity", None)
        return bool(identity and has_permission(identity, "audit.read"))

    column_list = [
        AuditEvent.sequence,
        AuditEvent.occurred_at,
        AuditEvent.actor_subject,
        AuditEvent.action,
        AuditEvent.resource_type,
        AuditEvent.resource_id,
        AuditEvent.outcome,
        AuditEvent.request_id,
    ]
    column_searchable_list = [
        AuditEvent.actor_subject,
        AuditEvent.actor_email,
        AuditEvent.action,
        AuditEvent.resource_type,
        AuditEvent.resource_id,
        AuditEvent.request_id,
        AuditEvent.event_hash,
    ]
    column_sortable_list = [
        AuditEvent.sequence,
        AuditEvent.occurred_at,
        AuditEvent.action,
        AuditEvent.outcome,
    ]
    column_default_sort = [(AuditEvent.sequence, True)]
    column_filters = [
        StaticValuesFilter(
            AuditEvent.outcome,
            [(value, value.title()) for value in ["succeeded", "failed", "skipped", "cancelled"]],
            title="Outcome",
        )
    ]
    can_create = False
    can_edit = False
    can_delete = False
    can_view_details = True
    can_export = True


class TemplateVersionAdmin(ModelView, model=TemplateVersion):
    name_plural = "Template Versions"
    icon = "fa-solid fa-code-branch"
    column_searchable_list = [TemplateVersion.source_revision]
    column_sortable_list = [TemplateVersion.created_at]
    column_default_sort = [(TemplateVersion.created_at, True)]
    column_list = [
        TemplateVersion.template,
        TemplateVersion.source_revision,
        TemplateVersion.created_at,
    ]
    can_create = False
    can_edit = False
    can_delete = False
    can_view_details = True


class TemplateAssetAdmin(ModelView, model=TemplateAsset):
    name_plural = "Template Assets"
    icon = "fa-solid fa-images"
    column_searchable_list = [TemplateAsset.url, TemplateAsset.kind, TemplateAsset.source]
    column_sortable_list = [
        TemplateAsset.kind,
        TemplateAsset.source,
        TemplateAsset.sort_order,
        TemplateAsset.created_at,
    ]
    column_default_sort = [(TemplateAsset.created_at, True)]
    column_filters = [
        StaticValuesFilter(
            TemplateAsset.kind,
            [(value, value.title()) for value in ["screenshot", "thumbnail", "preview", "image"]],
            title="Kind",
        ),
        StaticValuesFilter(
            TemplateAsset.source,
            [
                (value, value.title())
                for value in ["github", "gitlab", "bitbucket", "manual", "screenshot-service"]
            ],
            title="Source",
        ),
    ]
    column_list = [
        TemplateAsset.template,
        TemplateAsset.kind,
        TemplateAsset.source,
        TemplateAsset.sort_order,
        TemplateAsset.url,
    ]
    can_create = False
    can_edit = False
    can_delete = False
    can_view_details = True


class ScreenshotJobAdmin(ModelView, model=ScreenshotJob):
    name_plural = "Screenshot Jobs"
    icon = "fa-solid fa-camera"
    column_searchable_list = [
        ScreenshotJob.preview_url,
        ScreenshotJob.screenshot_url,
        ScreenshotJob.requested_by,
    ]
    column_sortable_list = [
        ScreenshotJob.status,
        ScreenshotJob.attempts,
        ScreenshotJob.created_at,
        ScreenshotJob.completed_at,
    ]
    column_default_sort = [(ScreenshotJob.created_at, True)]
    column_filters = [
        StaticValuesFilter(
            ScreenshotJob.status,
            [(item.name, item.value.title()) for item in ScreenshotJobStatus],
            title="Status",
        )
    ]
    column_list = [
        ScreenshotJob.template,
        ScreenshotJob.status,
        ScreenshotJob.attempts,
        ScreenshotJob.preview_url,
        ScreenshotJob.screenshot_url,
        ScreenshotJob.requested_by,
        ScreenshotJob.created_at,
        ScreenshotJob.completed_at,
    ]
    can_create = False
    can_edit = False
    can_delete = False
    can_view_details = True

    @action("retry", "Retry", "Retry the selected screenshot jobs?")
    async def retry(self, request: Request):
        raw = request.query_params.get("pks", "")
        try:
            identifiers = [UUID(value) for value in raw.split(",") if value]
        except ValueError as exc:
            raise ValidationError("Selected screenshot job identifiers are invalid") from exc
        return_url = _safe_admin_return_url(request, "/admin/screenshot-job/list")
        if not identifiers:
            return RedirectResponse(
                URL(return_url).include_query_params(error="No screenshot jobs were selected"),
                status_code=302,
            )
        require_permission(request, "media.write")
        container = self._admin_ref.app.state.container
        container.require_feature("operations_console", task=True)
        operation = await container.operation_service.create(
            operation_type="retry_screenshot_jobs",
            title=f"Retry {len(identifiers)} screenshot job(s)",
            requested_by=request.state.admin_identity.subject,
            requested_roles=list(request.state.admin_identity.roles),
            input_payload={"job_ids": [str(value) for value in identifiers]},
            return_url=return_url,
        )
        await container.operation_runner.enqueue(operation.id)
        return RedirectResponse(_operation_url(operation.id), status_code=302)


class _AdminBaseView(BaseView):
    def _csrf(self, request: Request, key: str) -> str:
        token = request.session.get(key)
        if not isinstance(token, str):
            token = secrets.token_urlsafe(32)
            request.session[key] = token
        return token

    @staticmethod
    def _validate_csrf(form: object, expected: str) -> None:
        submitted = str(form.get("csrf_token", ""))  # type: ignore[attr-defined]
        if not submitted or not compare_digest(submitted, expected):
            raise ValidationError("The form session expired. Reload the page and try again.")

    async def _choices(self) -> tuple[list[Category], list[Provider]]:
        async with async_session_factory() as session:
            categories = list(
                (await session.scalars(select(Category).where(Category.is_active.is_(True)))).all()
            )
            providers = list(
                (await session.scalars(select(Provider).where(Provider.is_active.is_(True)))).all()
            )
        return categories, providers

    async def _queue_operation(
        self,
        request: Request,
        *,
        operation_type: str,
        title: str,
        payload: dict[str, object],
        return_url: str,
    ) -> RedirectResponse:
        require_permission(request, _operation_permission(operation_type))
        container = self._admin_ref.app.state.container
        container.require_feature("operations_console", task=True)
        operation = await container.operation_service.create(
            operation_type=operation_type,
            title=title,
            requested_by=request.state.admin_identity.subject,
            requested_roles=list(request.state.admin_identity.roles),
            input_payload=payload,
            return_url=return_url,
        )
        await container.operation_runner.enqueue(operation.id)
        return RedirectResponse(_operation_url(operation.id), status_code=302)


class OperationsConsoleView(_AdminBaseView):
    name = "Operations"
    icon = "fa-solid fa-terminal"

    @expose("/operations", methods=["GET"])
    async def operations(self, request: Request):
        require_permission(request, "registry.read")
        container = self._admin_ref.app.state.container
        search = (request.query_params.get("q") or "").strip()
        status = (request.query_params.get("status") or "").strip()
        operation_type = (request.query_params.get("type") or "").strip()
        order = "asc" if request.query_params.get("order") == "asc" else "desc"
        operations = await container.operation_service.list_recent(
            search=search or None,
            status=status or None,
            operation_type=operation_type or None,
            order=order,
        )
        return await self.templates.TemplateResponse(
            request,
            "operations_list.html",
            {
                "title": "Operations Console",
                "operations": operations,
                "enabled": container.feature_enabled("operations_console"),
                "csrf_token": self._csrf(request, "operation_list_csrf"),
                "search": search,
                "status_filter": status,
                "type_filter": operation_type,
                "order": order,
                "operation_types": await container.operation_service.operation_types(),
                "operation_statuses": [item.value for item in OperationStatus],
                "message": request.query_params.get("message"),
            },
        )

    @expose("/operations/clear", methods=["POST"])
    async def clear_operations(self, request: Request):
        identity = require_permission(request, "operations.manage")
        form = await request.form()
        self._validate_csrf(form, self._csrf(request, "operation_list_csrf"))
        container = self._admin_ref.app.state.container
        scope = str(form.get("scope", "all_terminal"))
        count = await container.operation_service.clear_terminal(scope)
        await container.audit.append(
            action="operations.clear",
            resource_type="admin_operation",
            identity=identity,
            request=request,
            details={"scope": scope, "deleted_count": count},
        )
        return RedirectResponse(
            URL("/admin/operations").include_query_params(
                message=f"Cleared {count} terminal operation(s) and their logs"
            ),
            status_code=302,
        )

    @expose("/operations/{operation_id}", methods=["GET"])
    async def operation_detail(self, request: Request):
        require_permission(request, "registry.read")
        operation_id = UUID(request.path_params["operation_id"])
        operation = await self._admin_ref.app.state.container.operation_service.get(
            operation_id, with_logs=True
        )
        csrf_token = self._csrf(request, "operation_action_csrf")
        container = self._admin_ref.app.state.container
        template_summary = await _operation_template_summary(container, operation)
        return await self.templates.TemplateResponse(
            request,
            "operation_detail.html",
            {
                "title": operation.title,
                "operation": operation,
                "csrf_token": csrf_token,
                "terminal": operation.status.value in _TERMINAL_OPERATION_VALUES,
                "template_summary": template_summary,
            },
        )

    @expose("/operations/{operation_id}/status", methods=["GET"])
    async def operation_status(self, request: Request):
        require_permission(request, "registry.read")
        container = self._admin_ref.app.state.container
        operation = await container.operation_service.get(UUID(request.path_params["operation_id"]))
        template_summary = await _operation_template_summary(container, operation)
        return JSONResponse(
            {
                "id": str(operation.id),
                "status": operation.status.value,
                "progress": operation.progress,
                "error": operation.error_message,
                "result": operation.result_payload,
                "template": template_summary,
                "completed_at": operation.completed_at.isoformat()
                if operation.completed_at
                else None,
            }
        )

    @expose("/operations/{operation_id}/logs.json", methods=["GET"])
    async def operation_logs_json(self, request: Request):
        require_permission(request, "registry.read")
        operation_id = UUID(request.path_params["operation_id"])
        try:
            sequence = max(0, int(request.query_params.get("after", "0") or 0))
        except ValueError as exc:
            raise ValidationError("The log sequence must be an integer") from exc
        service = self._admin_ref.app.state.container.operation_service
        operation = await service.get(operation_id)
        logs = await service.logs_since(operation_id, sequence)
        return JSONResponse(
            {
                "operation_id": str(operation_id),
                "status": operation.status.value,
                "progress": operation.progress,
                "logs": [
                    {
                        "sequence": item.sequence,
                        "level": item.level,
                        "message": item.message,
                        "data": item.data,
                        "created_at": item.created_at.isoformat(),
                    }
                    for item in logs
                ],
            },
            headers={"Cache-Control": "no-store"},
        )

    @expose("/operations/{operation_id}/events", methods=["GET"])
    async def operation_events(self, request: Request):
        require_permission(request, "registry.read")
        operation_id = UUID(request.path_params["operation_id"])
        container = self._admin_ref.app.state.container
        service = container.operation_service

        async def stream():
            sequence = int(request.query_params.get("after", "0") or 0)
            while True:
                if await request.is_disconnected():
                    return
                operation = await service.get(operation_id)
                logs = await service.logs_since(operation_id, sequence)
                for item in logs:
                    sequence = item.sequence
                    payload = json.dumps(
                        {
                            "sequence": item.sequence,
                            "level": item.level,
                            "message": item.message,
                            "data": item.data,
                            "created_at": item.created_at.isoformat(),
                            "progress": operation.progress,
                            "status": operation.status.value,
                        },
                        separators=(",", ":"),
                    )
                    yield f"id: {item.sequence}\nevent: log\ndata: {payload}\n\n"
                template_summary = (
                    await _operation_template_summary(container, operation)
                    if operation.status.value in _TERMINAL_OPERATION_VALUES
                    else None
                )
                status_payload = json.dumps(
                    {
                        "status": operation.status.value,
                        "progress": operation.progress,
                        "error": operation.error_message,
                        "result": operation.result_payload,
                        "template": template_summary,
                    },
                    separators=(",", ":"),
                )
                yield f"event: status\ndata: {status_payload}\n\n"
                if operation.status.value in _TERMINAL_OPERATION_VALUES:
                    yield f"event: done\ndata: {status_payload}\n\n"
                    return
                await asyncio.sleep(0.75)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @expose("/operations/{operation_id}/logs.txt", methods=["GET"])
    async def operation_logs(self, request: Request):
        require_permission(request, "registry.read")
        operation = await self._admin_ref.app.state.container.operation_service.get(
            UUID(request.path_params["operation_id"]), with_logs=True
        )
        lines = [
            f"RegHub operation: {operation.title}",
            f"ID: {operation.id}",
            f"Status: {operation.status.value}",
            "=" * 88,
        ]
        lines.extend(
            (
                f"{item.created_at.isoformat()} [{item.level.upper()}] {item.message}"
                + (
                    " "
                    + json.dumps(item.data, ensure_ascii=False, separators=(",", ":"), default=str)
                    if item.data
                    else ""
                )
            )
            for item in operation.logs
        )
        return PlainTextResponse(
            "\n".join(lines) + "\n",
            headers={
                "Content-Disposition": f'attachment; filename="reghub-operation-{operation.id}.txt"'
            },
        )

    @expose("/operations/{operation_id}/retry", methods=["POST"])
    async def retry_operation(self, request: Request):
        csrf = self._csrf(request, "operation_action_csrf")
        form = await request.form()
        self._validate_csrf(form, csrf)
        container = self._admin_ref.app.state.container
        original_id = UUID(request.path_params["operation_id"])
        original = await container.operation_service.get(original_id)
        identity = require_permission(request, _operation_permission(original.operation_type))
        operation = await container.operation_service.clone_for_retry(
            original_id,
            identity.subject,
            requested_roles=list(identity.roles),
        )
        await container.operation_runner.enqueue(operation.id)
        return RedirectResponse(_operation_url(operation.id), status_code=302)

    @expose("/operations/{operation_id}/continue-update", methods=["POST"])
    async def continue_duplicate_update(self, request: Request):
        require_permission(request, "sync.run")
        csrf = self._csrf(request, "operation_action_csrf")
        form = await request.form()
        self._validate_csrf(form, csrf)
        container = self._admin_ref.app.state.container
        source = await container.operation_service.get(UUID(request.path_params["operation_id"]))
        result = source.result_payload or {}
        if (
            source.status != OperationStatus.SKIPPED
            or result.get("outcome") != "already_exists"
            or not result.get("template_id")
        ):
            raise ValidationError("Only an already-imported repository can continue as an update")
        template_id = UUID(str(result["template_id"]))
        template_name = str(
            result.get("template_name") or result.get("template_slug") or template_id
        )
        operation = await container.operation_service.create(
            operation_type="sync_templates",
            title=f"Update imported template: {template_name}",
            requested_by=request.state.admin_identity.subject,
            requested_roles=list(request.state.admin_identity.roles),
            input_payload={"template_ids": [str(template_id)]},
            return_url=f"/admin/template/details/{template_id}",
            retry_of_id=source.id,
        )
        await container.operation_runner.enqueue(operation.id)
        return RedirectResponse(_operation_url(operation.id), status_code=302)

    @expose("/operations/{operation_id}/cancel", methods=["POST"])
    async def cancel_operation(self, request: Request):
        csrf = self._csrf(request, "operation_action_csrf")
        form = await request.form()
        self._validate_csrf(form, csrf)
        operation_id = UUID(request.path_params["operation_id"])
        container = self._admin_ref.app.state.container
        operation = await container.operation_service.get(operation_id)
        identity = require_permission(request, "operations.run")
        if operation.requested_by != identity.subject and not has_permission(
            identity, "operations.manage"
        ):
            raise PermissionDeniedError(
                "Only the requester or an operations administrator can cancel this task"
            )
        await container.operation_runner.request_cancel(operation_id)
        return RedirectResponse(_operation_url(operation_id), status_code=302)


class GovernanceView(_AdminBaseView):
    def is_accessible(self, request: Request) -> bool:
        identity = getattr(request.state, "admin_identity", None)
        return bool(identity and has_permission(identity, "audit.read"))

    name = "Governance"
    icon = "fa-solid fa-user-shield"

    @expose("/governance", methods=["GET"])
    async def governance(self, request: Request):
        identity = require_permission(request, "audit.read")
        container = self._admin_ref.app.state.container
        verification = await container.audit.verify()
        worker_status = await container.operation_runner.worker_status()
        settings = container.settings
        return await self.templates.TemplateResponse(
            request,
            "governance.html",
            {
                "title": "Production Governance",
                "identity": identity,
                "permissions": sorted(permissions_for_roles(identity.roles)),
                "audit_verification": verification,
                "worker_status": worker_status,
                "operation_backend": settings.operation_backend,
                "effective_operation_backend": container.operation_runner.effective_backend,
                "redis_worker_enabled": container.operation_runner.redis_worker_enabled,
                "redis_configured": container.operation_runner.redis_configured,
                "cache_backend": container.catalog_cache.backend_name,
                "rate_limit_backend": container.rate_limiter.backend_name,
                "trusted_proxy_networks": settings.trusted_proxy_networks,
                "dedicated_runtime_key": bool(settings.runtime_encryption_key),
                "dedicated_audit_key": bool(settings.audit_signing_key),
                "primary_runtime_key_id": container.runtime_settings.primary_encryption_key_id,
                "primary_audit_key_id": container.audit.primary_key_id,
            },
        )


class SettingsView(_AdminBaseView):
    def is_accessible(self, request: Request) -> bool:
        identity = getattr(request.state, "admin_identity", None)
        return bool(identity and has_permission(identity, "settings.manage"))

    name = "Settings"
    icon = "fa-solid fa-sliders"

    @staticmethod
    def _bool(form: object, key: str) -> bool:
        return str(form.get(key, "")).casefold() in {  # type: ignore[attr-defined]
            "1",
            "true",
            "on",
            "yes",
        }

    @expose("/settings", methods=["GET", "POST"])
    async def settings(self, request: Request):
        require_permission(request, "settings.manage")
        csrf_token = self._csrf(request, "settings_csrf")
        container = self._admin_ref.app.state.container
        api_access = getattr(container, "api_access", None)
        success: str | None = None
        error: str | None = None
        new_api_token: str | None = None
        active_pane = _settings_pane(request.query_params.get("tab"))
        if request.method == "POST":
            form = await request.form()
            action_name = str(form.get("action", ""))
            active_pane = _settings_pane(form.get("return_tab"), action_name)
            try:
                self._validate_csrf(form, csrf_token)
                identity = request.state.admin_identity.subject
                if action_name == "save_features":
                    features = await container.runtime_settings.feature_rows()
                    feature_updates = {
                        item.key: (
                            self._bool(form, f"enabled__{item.key}"),
                            self._bool(form, f"task__{item.key}"),
                        )
                        for item in features
                    }
                    current_redis_worker = next(
                        (item.enabled for item in features if item.key == "redis_worker"), False
                    )
                    requested_redis_worker = feature_updates.get(
                        "redis_worker", (False, True)
                    )[0]
                    # Enabling the durable queue is safe only after both Redis and the
                    # standalone worker are genuinely available. Validate before the
                    # database mutation so a failed activation never leaves a misleading
                    # ON state in Settings.
                    if requested_redis_worker and not current_redis_worker:
                        await container.operation_runner.validate_redis_worker_activation()
                    await container.runtime_settings.update_features_bulk(
                        feature_updates,
                        updated_by=identity,
                    )
                    await container.reload_runtime()
                    await container.apply_runtime_infrastructure()
                    success = "Feature controls updated immediately. No web redeploy was required."
                elif action_name == "save_integration":
                    raw_config = str(form.get("config_json", "{}")).strip() or "{}"
                    config = json.loads(raw_config)
                    if not isinstance(config, dict):
                        raise ValidationError("Integration config JSON must be an object")
                    await container.runtime_settings.upsert_integration(
                        slug=str(form.get("slug", "")),
                        name=str(form.get("name", "")),
                        integration_type=str(form.get("integration_type", "custom")),
                        enabled=self._bool(form, "enabled"),
                        base_url=str(form.get("base_url", "")) or None,
                        username=str(form.get("username", "")) or None,
                        secret=str(form.get("secret", "")) or None,
                        clear_secret=self._bool(form, "clear_secret"),
                        use_environment_fallback=self._bool(form, "use_environment_fallback"),
                        config=config,
                        updated_by=identity,
                    )
                    await container.reload_runtime()
                    success = "Integration configuration saved and loaded immediately."
                elif action_name == "remove_integration":
                    await container.runtime_settings.remove_integration(
                        str(form.get("slug", "")), updated_by=identity
                    )
                    await container.reload_runtime()
                    success = "Integration runtime configuration removed or disabled."
                elif action_name == "reload_runtime":
                    await container.reload_runtime()
                    await container.apply_runtime_infrastructure()
                    success = "Runtime configuration reloaded."
                elif action_name == "save_api_mode":
                    if api_access is None:
                        raise ValidationError("API access management is unavailable")
                    await api_access.set_mode(str(form.get("api_mode", "development")), identity)
                    success = "API access mode updated immediately."
                elif action_name == "create_api_token":
                    expires_raw = str(form.get("expires_at", "")).strip()
                    expires_at = (
                        datetime.fromisoformat(expires_raw).replace(tzinfo=UTC)
                        if expires_raw
                        else None
                    )
                    if api_access is None:
                        raise ValidationError("API access management is unavailable")
                    _row, new_api_token = await api_access.create_token(
                        name=str(form.get("token_name", "")),
                        scopes=[str(value) for value in form.getlist("scopes")],
                        description=str(form.get("description", "")) or None,
                        expires_at=expires_at,
                        created_by=identity,
                    )
                    success = "Service token created. Copy it now; RegHub will not show it again."
                elif action_name == "toggle_api_token":
                    if api_access is None:
                        raise ValidationError("API access management is unavailable")
                    await api_access.set_token_enabled(
                        UUID(str(form.get("token_id", ""))),
                        self._bool(form, "enabled"),
                        identity,
                    )
                    success = "Service token state updated."
                elif action_name == "delete_api_token":
                    if api_access is None:
                        raise ValidationError("API access management is unavailable")
                    await api_access.delete_token(UUID(str(form.get("token_id", ""))))
                    success = "Service token deleted."
                elif action_name == "add_block_rule":
                    if api_access is None:
                        raise ValidationError("API access management is unavailable")
                    await api_access.add_block_rule(
                        value=str(form.get("block_value", "")),
                        note=str(form.get("note", "")) or None,
                        created_by=identity,
                    )
                    success = "API block rule added."
                elif action_name == "update_block_rule":
                    if api_access is None:
                        raise ValidationError("API access management is unavailable")
                    await api_access.update_block_rule(
                        UUID(str(form.get("rule_id", ""))),
                        value=str(form.get("block_value", "")),
                        enabled=self._bool(form, "enabled"),
                        note=str(form.get("note", "")) or None,
                        updated_by=identity,
                    )
                    success = "API block rule updated."
                elif action_name == "delete_block_rule":
                    if api_access is None:
                        raise ValidationError("API access management is unavailable")
                    await api_access.delete_block_rule(UUID(str(form.get("rule_id", ""))))
                    success = "API block rule deleted."
                else:
                    raise ValidationError("Unsupported settings action")
                await container.catalog_cache.invalidate_all()
                await container.audit.append(
                    action=f"settings.{action_name}",
                    resource_type="runtime_settings",
                    identity=request.state.admin_identity,
                    request=request,
                    details={"active_pane": active_pane},
                )
            except json.JSONDecodeError:
                error = "Integration config JSON is invalid"
            except (RegistryError, ValueError) as exc:
                error = str(exc)
            except Exception:
                logger.exception("Unexpected settings update failure")
                error = "Settings update failed unexpectedly. Check application logs."

        features = await container.runtime_settings.feature_rows()
        integrations = await container.runtime_settings.integration_rows()
        integration_cards = []
        for item in integrations:
            status = container.runtime_settings.integration_status(item)
            integration_cards.append(
                {
                    "row": item,
                    "status": status,
                    "config_json": json.dumps(item.config or {}, indent=2, sort_keys=True),
                }
            )
        grouped_features: dict[str, list[object]] = {}
        for feature in features:
            grouped_features.setdefault(feature.category, []).append(feature)

        published_slug: str | None = None
        session_factory = getattr(container, "session_factory", None)
        if session_factory is not None:
            async with session_factory() as session:
                published_slug = await session.scalar(
                    select(Template.slug)
                    .where(Template.status == TemplateStatus.PUBLISHED)
                    .order_by(Template.updated_at.desc())
                    .limit(1)
                )
        api_endpoint_rows = endpoint_rows(published_slug)
        return await self.templates.TemplateResponse(
            request,
            "settings.html",
            {
                "title": "RegHub Settings",
                "csrf_token": csrf_token,
                "feature_groups": grouped_features,
                "integration_cards": integration_cards,
                "success": success,
                "error": error,
                "api_mode": api_access.mode if api_access else "development",
                "api_tokens": await api_access.token_rows() if api_access else [],
                "api_block_rules": await api_access.block_rule_rows() if api_access else [],
                "api_scopes": api_access.SCOPES if api_access else [],
                "new_api_token": new_api_token,
                "active_pane": active_pane,
                "api_endpoint_rows": api_endpoint_rows,
                "published_template_slug": published_slug,
            },
        )

    @expose("/settings/action", methods=["POST"])
    async def settings_action(self, request: Request):
        """Stable AJAX endpoint for every Settings mutation.

        SQLAdmin custom GET/POST view routing can be affected by reverse-proxy
        method handling when the same URL serves both page rendering and form
        mutation. Keeping a dedicated POST route avoids that ambiguity while
        preserving the original POST /settings route as a no-JavaScript
        fallback. The regular renderer is reused so the browser receives the
        authoritative, freshly rendered pane and one-time token values.
        """
        return await self.settings(request)

    @expose("/settings/api-check", methods=["POST"])
    async def api_check(self, request: Request):
        require_permission(request, "api.manage")
        form = await request.form()
        self._validate_csrf(form, self._csrf(request, "settings_csrf"))
        container = self._admin_ref.app.state.container
        api_access = getattr(container, "api_access", None)
        if api_access is None:
            raise ValidationError("API access management is unavailable")

        requested_key = str(form.get("endpoint_id", "")).strip()
        requested_endpoint = endpoint_by_key(requested_key) if requested_key else None
        if requested_key and requested_endpoint is None:
            raise ValidationError("Unknown API endpoint check")

        published_slug: str | None = None
        session_factory = getattr(container, "session_factory", None)
        if session_factory is not None:
            async with session_factory() as session:
                published_slug = await session.scalar(
                    select(Template.slug)
                    .where(Template.status == TemplateStatus.PUBLISHED)
                    .order_by(Template.updated_at.desc())
                    .limit(1)
                )

        definitions = (
            [requested_endpoint]
            if requested_endpoint
            else [endpoint_by_key(str(item["key"])) for item in endpoint_rows(published_slug)]
        )
        definitions = [item for item in definitions if item is not None]
        token = api_access.issue_check_token()
        import httpx

        results: list[dict[str, object]] = []
        root_app = self._admin_ref.app
        transport = httpx.ASGITransport(app=root_app, raise_app_exceptions=False)
        base_url = f"{request.url.scheme}://{request.url.netloc}"
        async with httpx.AsyncClient(
            transport=transport,
            base_url=base_url,
            timeout=15,
            follow_redirects=False,
        ) as client:
            for endpoint in definitions:
                path = endpoint.concrete_path(published_slug)
                if path is None:
                    results.append(
                        {
                            "endpoint_id": endpoint.key,
                            "name": endpoint.name,
                            "path": endpoint.path_template,
                            "method": endpoint.method,
                            "scope": endpoint.scope,
                            "status": "SKIP",
                            "ok": False,
                            "skipped": True,
                            "duration_ms": 0,
                            "body": "Publish at least one template to check this dynamic endpoint.",
                        }
                    )
                    continue
                started = datetime.now(UTC)
                try:
                    response = await client.request(
                        endpoint.method,
                        path,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "X-Request-ID": f"admin-api-check-{endpoint.key}",
                            "Accept": "application/json",
                        },
                    )
                    elapsed = int((datetime.now(UTC) - started).total_seconds() * 1000)
                    content_type = response.headers.get("content-type", "")
                    body: object
                    if "application/json" in content_type:
                        try:
                            body = response.json()
                        except ValueError:
                            body = response.text[:1000]
                    else:
                        body = response.text[:1000]
                    results.append(
                        {
                            "endpoint_id": endpoint.key,
                            "name": endpoint.name,
                            "path": path,
                            "method": endpoint.method,
                            "scope": endpoint.scope,
                            "status": response.status_code,
                            "ok": response.status_code < 400,
                            "skipped": False,
                            "duration_ms": elapsed,
                            "body": body,
                            "request_id": response.headers.get("x-request-id"),
                        }
                    )
                except Exception as exc:
                    logger.exception("Administrator API check failed for %s", endpoint.key)
                    results.append(
                        {
                            "endpoint_id": endpoint.key,
                            "name": endpoint.name,
                            "path": path,
                            "method": endpoint.method,
                            "scope": endpoint.scope,
                            "status": 0,
                            "ok": False,
                            "skipped": False,
                            "duration_ms": 0,
                            "body": f"{exc.__class__.__name__}: {exc}",
                        }
                    )
        return JSONResponse(
            {
                "mode": api_access.mode,
                "checked_at": datetime.now(UTC).isoformat(),
                "results": results,
            },
            headers={"Cache-Control": "no-store"},
        )


class GitHubImportView(_AdminBaseView):
    name = "GitHub Import"
    icon = "fa-brands fa-github"

    @expose("/github-import", methods=["GET", "POST"])
    async def github_import(self, request: Request):
        require_permission(request, "registry.read")
        if request.method == "POST":
            require_permission(request, "imports.run")
        csrf_token = self._csrf(request, "github_import_csrf")
        categories, providers = await self._choices()
        container = self._admin_ref.app.state.container
        feature_flag_enabled = container.feature_enabled("github_import", task=True)
        integration_enabled = "github" in container.adapter_names
        enabled = feature_flag_enabled and integration_enabled
        context: dict[str, object] = {
            "title": "Import GitHub Repository",
            "csrf_token": csrf_token,
            "categories": categories,
            "providers": providers,
            "github_authenticated": container.github_authenticated,
            "feature_enabled": enabled,
            "feature_flag_enabled": feature_flag_enabled,
            "integration_enabled": integration_enabled,
        }
        if request.method == "POST":
            form = await request.form()
            try:
                self._validate_csrf(form, csrf_token)
                container.require_feature("github_import", task=True)
                return await self._queue_operation(
                    request,
                    operation_type="import_repository",
                    title="Import GitHub repository",
                    payload={
                        "adapter": "github",
                        "repository_url": str(form.get("repository_url", "")).strip(),
                        "category_id": str(form.get("category_id", "")) or None,
                        "provider_id": str(form.get("provider_id", "")) or None,
                    },
                    return_url="/admin/github-import",
                )
            except (RegistryError, ValueError) as exc:
                context["error"] = str(exc)
        return await self.templates.TemplateResponse(request, "github_import.html", context)


class RegistryImportView(_AdminBaseView):
    name = "Registry Import"
    icon = "fa-solid fa-cloud-arrow-down"

    @expose("/registry-import", methods=["GET", "POST"])
    async def registry_import(self, request: Request):
        require_permission(request, "registry.read")
        if request.method == "POST":
            require_permission(request, "imports.run")
        csrf_token = self._csrf(request, "registry_import_csrf")
        categories, providers = await self._choices()
        container = self._admin_ref.app.state.container
        context: dict[str, object] = {
            "title": "Import External Registry Repository",
            "csrf_token": csrf_token,
            "categories": categories,
            "providers": providers,
            "adapters": [
                name
                for name in container.adapter_names
                if name != "github" and container.feature_enabled(f"{name}_import", task=True)
            ],
            "gitlab_authenticated": container.gitlab_authenticated,
            "bitbucket_authenticated": container.bitbucket_authenticated,
        }
        if request.method == "POST":
            form = await request.form()
            try:
                self._validate_csrf(form, csrf_token)
                adapter = str(form.get("adapter", ""))
                container.require_feature(f"{adapter}_import", task=True)
                return await self._queue_operation(
                    request,
                    operation_type="import_repository",
                    title=f"Import {adapter.title()} repository",
                    payload={
                        "adapter": adapter,
                        "repository_url": str(form.get("repository_url", "")).strip(),
                        "category_id": str(form.get("category_id", "")) or None,
                        "provider_id": str(form.get("provider_id", "")) or None,
                    },
                    return_url="/admin/registry-import",
                )
            except (RegistryError, ValueError) as exc:
                context["error"] = str(exc)
        return await self.templates.TemplateResponse(request, "registry_import.html", context)


class LocalImportView(_AdminBaseView):
    name = "Local Import"
    icon = "fa-solid fa-file-zipper"

    @expose("/local-import", methods=["GET", "POST"])
    async def local_import(self, request: Request):
        require_permission(request, "registry.read")
        if request.method == "POST":
            require_permission(request, "imports.run")
        csrf_token = self._csrf(request, "local_import_csrf")
        categories, providers = await self._choices()
        container = self._admin_ref.app.state.container
        context: dict[str, object] = {
            "title": "Import Local Manifest or ZIP",
            "csrf_token": csrf_token,
            "categories": categories,
            "providers": providers,
            "local_upload_enabled": container.local_upload_enabled,
            "max_bytes": container.local_upload_max_bytes,
        }
        if request.method == "POST":
            form = await request.form()
            try:
                self._validate_csrf(form, csrf_token)
                container.require_feature("local_import", task=True)
                import_type = str(form.get("import_type", "manifest"))
                common = {
                    "category_id": str(form.get("category_id", "")) or None,
                    "provider_id": str(form.get("provider_id", "")) or None,
                }
                if import_type == "manifest":
                    payload = json.loads(str(form.get("manifest_json", "")))
                    if not isinstance(payload, dict):
                        raise ValidationError("Manifest JSON must be an object")
                    return await self._queue_operation(
                        request,
                        operation_type="import_local_manifest",
                        title="Import local manifest",
                        payload={**common, "manifest": payload},
                        return_url="/admin/local-import",
                    )
                if import_type == "zip":
                    upload = form.get("zip_file")
                    if not isinstance(upload, UploadFile) or not upload.filename:
                        raise ValidationError("Select a ZIP file")
                    data = await upload.read(container.local_upload_max_bytes + 1)
                    if len(data) > container.local_upload_max_bytes:
                        raise ValidationError("ZIP exceeds the configured maximum upload size")
                    temporary_path = await asyncio.to_thread(_write_temporary_zip, data)
                    return await self._queue_operation(
                        request,
                        operation_type="import_local_zip",
                        title=f"Inspect and import {upload.filename}",
                        payload={
                            **common,
                            "filename": upload.filename,
                            "temporary_path": temporary_path,
                        },
                        return_url="/admin/local-import",
                    )
                raise ValidationError("Unsupported local import type")
            except json.JSONDecodeError:
                context["error"] = "Manifest JSON is invalid"
            except (RegistryError, ValueError) as exc:
                context["error"] = str(exc)
        return await self.templates.TemplateResponse(request, "local_import.html", context)


class AssetGalleryView(_AdminBaseView):
    name = "Asset Gallery"
    icon = "fa-solid fa-photo-film"

    @expose("/asset-gallery", methods=["GET", "POST"])
    async def asset_gallery(self, request: Request):
        require_permission(request, "registry.read")
        if request.method == "POST":
            require_permission(request, "media.write")
        csrf_token = self._csrf(request, "asset_gallery_csrf")
        selected_template_id = request.query_params.get("template_id")
        success: str | None = None
        error: str | None = None
        container = self._admin_ref.app.state.container
        if request.method == "POST":
            form = await request.form()
            try:
                self._validate_csrf(form, csrf_token)
                container.require_feature("asset_gallery", task=True)
                action_name = str(form.get("action", "add"))
                template_id = UUID(str(form.get("template_id", "")))
                async with async_session_factory() as session:
                    if action_name == "add":
                        await TemplateAssetService.add_manual(
                            session,
                            template_id=template_id,
                            url=str(form.get("url", "")),
                            kind=str(form.get("kind", "screenshot")),
                            sort_order=int(str(form.get("sort_order", "0")) or "0"),
                        )
                        success = "Asset added."
                    elif action_name == "update":
                        await TemplateAssetService.update_manual(
                            session,
                            asset_id=UUID(str(form.get("asset_id", ""))),
                            url=str(form.get("url", "")),
                            kind=str(form.get("kind", "screenshot")),
                            sort_order=int(str(form.get("sort_order", "0")) or "0"),
                        )
                        success = "Asset updated."
                    elif action_name == "delete":
                        await TemplateAssetService.delete_manual(
                            session, UUID(str(form.get("asset_id", "")))
                        )
                        success = "Asset deleted."
                    else:
                        raise ValidationError("Unsupported gallery action")
                selected_template_id = str(template_id)
                await container.catalog_cache.invalidate_all()
                await container.audit.append(
                    action=f"asset.{action_name}",
                    resource_type="template_asset",
                    resource_id=str(template_id),
                    identity=request.state.admin_identity,
                    request=request,
                    details={"kind": str(form.get("kind", ""))},
                )
            except (RegistryError, ValueError) as exc:
                error = str(exc)
            except Exception:
                logger.exception("Unexpected asset gallery failure")
                error = "Asset operation failed unexpectedly. Check the application logs."

        template_query = (request.query_params.get("q") or "").strip()
        asset_query = (request.query_params.get("asset_q") or "").strip()
        asset_kind = (request.query_params.get("kind") or "").strip()
        async with async_session_factory() as session:
            selected = None
            if selected_template_id:
                try:
                    selected = await session.get(Template, UUID(selected_template_id))
                except ValueError:
                    selected = None
            template_statement = select(Template)
            if template_query:
                term = f"%{template_query}%"
                template_statement = template_statement.where(
                    or_(
                        Template.name.ilike(term),
                        Template.slug.ilike(term),
                        Template.repository_url.ilike(term),
                    )
                )
            templates = list(
                (await session.scalars(template_statement.order_by(Template.name).limit(100))).all()
            )
            if selected and all(item.id != selected.id for item in templates):
                templates.insert(0, selected)
            assets: list[TemplateAsset] = []
            if selected:
                asset_statement = select(TemplateAsset).where(
                    TemplateAsset.template_id == selected.id
                )
                if asset_query:
                    term = f"%{asset_query}%"
                    asset_statement = asset_statement.where(
                        or_(
                            TemplateAsset.url.ilike(term),
                            TemplateAsset.source.ilike(term),
                            TemplateAsset.kind.ilike(term),
                        )
                    )
                if asset_kind:
                    asset_statement = asset_statement.where(TemplateAsset.kind == asset_kind)
                assets = list(
                    (
                        await session.scalars(
                            asset_statement.order_by(
                                TemplateAsset.sort_order, TemplateAsset.created_at
                            )
                        )
                    ).all()
                )
        return await self.templates.TemplateResponse(
            request,
            "asset_gallery.html",
            {
                "title": "Template Asset Gallery",
                "csrf_token": csrf_token,
                "templates": templates,
                "selected": selected,
                "assets": assets,
                "success": success,
                "error": error,
                "feature_enabled": container.feature_enabled("asset_gallery", task=True),
                "template_query": template_query,
                "asset_query": asset_query,
                "asset_kind": asset_kind,
            },
        )
