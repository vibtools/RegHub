import asyncio
import json
import logging
import secrets
import tempfile
from hmac import compare_digest
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from sqladmin import BaseView, ModelView, action, expose
from sqladmin.filters import BooleanFilter, ForeignKeyFilter, StaticValuesFilter
from sqlalchemy import select
from starlette.datastructures import URL, UploadFile
from starlette.requests import Request
from starlette.responses import (
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    StreamingResponse,
)

from app.core.enums import OperationStatus, TemplateStatus
from app.core.exceptions import RegistryError, ValidationError
from app.database.session import async_session_factory
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

logger = logging.getLogger(__name__)
_TERMINAL_OPERATION_VALUES = {
    OperationStatus.SUCCEEDED.value,
    OperationStatus.FAILED.value,
    OperationStatus.CANCELLED.value,
}


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


def _write_temporary_zip(data: bytes) -> str:
    temp_dir = Path(tempfile.gettempdir()) / "reghub-operations"
    temp_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb", suffix=".zip", prefix="upload-", dir=temp_dir, delete=False
    ) as handle:
        handle.write(data)
        return handle.name


class CategoryAdmin(ModelView, model=Category):
    name = "Category"
    name_plural = "Categories"
    icon = "fa-solid fa-folder-tree"
    column_list = [Category.name, Category.slug, Category.is_active, Category.updated_at]
    column_searchable_list = [Category.name, Category.slug]
    column_sortable_list = [Category.name, Category.created_at, Category.updated_at]
    form_excluded_columns = [Category.templates, Category.created_at, Category.updated_at]


class ProviderAdmin(ModelView, model=Provider):
    icon = "fa-solid fa-building"
    column_list = [Provider.name, Provider.slug, Provider.provider_type, Provider.is_active]
    column_searchable_list = [Provider.name, Provider.slug]
    form_excluded_columns = [Provider.templates, Provider.created_at, Provider.updated_at]


class FrameworkAdmin(ModelView, model=Framework):
    icon = "fa-solid fa-layer-group"
    column_list = [Framework.name, Framework.slug, Framework.is_active, Framework.updated_at]
    column_searchable_list = [Framework.name, Framework.slug]
    form_excluded_columns = [Framework.templates, Framework.created_at, Framework.updated_at]


class TemplateAdmin(ModelView, model=Template):
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
        Template.updated_at,
    ]
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
        container = self._admin_ref.app.state.container
        container.require_feature("operations_console", task=True)
        operation = await container.operation_service.create(
            operation_type=operation_type,
            title=title,
            requested_by=request.state.admin_identity.subject,
            input_payload=payload,
            return_url=_safe_admin_return_url(request),
        )
        container.operation_runner.enqueue(operation.id)
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


class TemplateVersionAdmin(ModelView, model=TemplateVersion):
    name_plural = "Template Versions"
    icon = "fa-solid fa-code-branch"
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
        container = self._admin_ref.app.state.container
        container.require_feature("operations_console", task=True)
        operation = await container.operation_service.create(
            operation_type="retry_screenshot_jobs",
            title=f"Retry {len(identifiers)} screenshot job(s)",
            requested_by=request.state.admin_identity.subject,
            input_payload={"job_ids": [str(value) for value in identifiers]},
            return_url=return_url,
        )
        container.operation_runner.enqueue(operation.id)
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
        container = self._admin_ref.app.state.container
        container.require_feature("operations_console", task=True)
        operation = await container.operation_service.create(
            operation_type=operation_type,
            title=title,
            requested_by=request.state.admin_identity.subject,
            input_payload=payload,
            return_url=return_url,
        )
        container.operation_runner.enqueue(operation.id)
        return RedirectResponse(_operation_url(operation.id), status_code=302)


class OperationsConsoleView(_AdminBaseView):
    name = "Operations"
    icon = "fa-solid fa-terminal"

    @expose("/operations", methods=["GET"])
    async def operations(self, request: Request):
        container = self._admin_ref.app.state.container
        operations = await container.operation_service.list_recent()
        return await self.templates.TemplateResponse(
            request,
            "operations_list.html",
            {
                "title": "Operations Console",
                "operations": operations,
                "enabled": container.feature_enabled("operations_console"),
            },
        )

    @expose("/operations/{operation_id}", methods=["GET"])
    async def operation_detail(self, request: Request):
        operation_id = UUID(request.path_params["operation_id"])
        operation = await self._admin_ref.app.state.container.operation_service.get(
            operation_id, with_logs=True
        )
        csrf_token = self._csrf(request, "operation_action_csrf")
        return await self.templates.TemplateResponse(
            request,
            "operation_detail.html",
            {
                "title": operation.title,
                "operation": operation,
                "csrf_token": csrf_token,
                "terminal": operation.status.value in _TERMINAL_OPERATION_VALUES,
            },
        )

    @expose("/operations/{operation_id}/status", methods=["GET"])
    async def operation_status(self, request: Request):
        operation = await self._admin_ref.app.state.container.operation_service.get(
            UUID(request.path_params["operation_id"])
        )
        return JSONResponse(
            {
                "id": str(operation.id),
                "status": operation.status.value,
                "progress": operation.progress,
                "error": operation.error_message,
                "result": operation.result_payload,
                "completed_at": operation.completed_at.isoformat()
                if operation.completed_at
                else None,
            }
        )

    @expose("/operations/{operation_id}/events", methods=["GET"])
    async def operation_events(self, request: Request):
        operation_id = UUID(request.path_params["operation_id"])
        service = self._admin_ref.app.state.container.operation_service

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
                status_payload = json.dumps(
                    {
                        "status": operation.status.value,
                        "progress": operation.progress,
                        "error": operation.error_message,
                        "result": operation.result_payload,
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
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @expose("/operations/{operation_id}/logs.txt", methods=["GET"])
    async def operation_logs(self, request: Request):
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
            f"{item.created_at.isoformat()} [{item.level.upper()}] {item.message}"
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
        operation = await container.operation_service.clone_for_retry(
            UUID(request.path_params["operation_id"]), request.state.admin_identity.subject
        )
        container.operation_runner.enqueue(operation.id)
        return RedirectResponse(_operation_url(operation.id), status_code=302)

    @expose("/operations/{operation_id}/cancel", methods=["POST"])
    async def cancel_operation(self, request: Request):
        csrf = self._csrf(request, "operation_action_csrf")
        form = await request.form()
        self._validate_csrf(form, csrf)
        operation_id = UUID(request.path_params["operation_id"])
        await self._admin_ref.app.state.container.operation_runner.request_cancel(operation_id)
        return RedirectResponse(_operation_url(operation_id), status_code=302)


class SettingsView(_AdminBaseView):
    name = "Settings"
    icon = "fa-solid fa-sliders"

    @staticmethod
    def _bool(form: object, key: str) -> bool:
        return str(form.get(key, "")).casefold() in {"1", "true", "on", "yes"}  # type: ignore[attr-defined]

    @expose("/settings", methods=["GET", "POST"])
    async def settings(self, request: Request):
        csrf_token = self._csrf(request, "settings_csrf")
        container = self._admin_ref.app.state.container
        success: str | None = None
        error: str | None = None
        if request.method == "POST":
            form = await request.form()
            try:
                self._validate_csrf(form, csrf_token)
                action_name = str(form.get("action", ""))
                identity = request.state.admin_identity.subject
                if action_name == "save_features":
                    features = await container.runtime_settings.feature_rows()
                    await container.runtime_settings.update_features_bulk(
                        {
                            item.key: (
                                self._bool(form, f"enabled__{item.key}"),
                                self._bool(form, f"task__{item.key}"),
                            )
                            for item in features
                        },
                        updated_by=identity,
                    )
                    await container.reload_runtime()
                    success = "Feature controls updated immediately. No redeploy was required."
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
                    success = "Runtime configuration reloaded."
                else:
                    raise ValidationError("Unsupported settings action")
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
            },
        )


class GitHubImportView(_AdminBaseView):
    name = "GitHub Import"
    icon = "fa-brands fa-github"

    @expose("/github-import", methods=["GET", "POST"])
    async def github_import(self, request: Request):
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
            except (RegistryError, ValueError) as exc:
                error = str(exc)
            except Exception:
                logger.exception("Unexpected asset gallery failure")
                error = "Asset operation failed unexpectedly. Check the application logs."

        async with async_session_factory() as session:
            templates = list(
                (await session.scalars(select(Template).order_by(Template.name))).all()
            )
            selected = None
            assets: list[TemplateAsset] = []
            if selected_template_id:
                try:
                    selected = await session.get(Template, UUID(selected_template_id))
                except ValueError:
                    selected = None
            if selected:
                assets = await TemplateAssetService.list_for_template(session, selected.id)
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
            },
        )
