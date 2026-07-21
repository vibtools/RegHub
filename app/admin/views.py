import json
import logging
import secrets
from hmac import compare_digest
from uuid import UUID

from sqladmin import BaseView, ModelView, action, expose
from sqladmin.filters import BooleanFilter, ForeignKeyFilter, StaticValuesFilter
from sqlalchemy import select
from starlette.datastructures import URL, UploadFile
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.core.enums import TemplateStatus
from app.core.exceptions import RegistryError, ValidationError
from app.database.session import async_session_factory
from app.models.category import Category
from app.models.framework import Framework
from app.models.import_history import ImportHistory
from app.models.provider import Provider
from app.models.sync_history import SyncHistory
from app.models.template import Template
from app.models.template_asset import TemplateAsset
from app.models.template_version import TemplateVersion
from app.registry.local import repository_from_manifest, repository_from_zip
from app.registry.template import TemplateService

logger = logging.getLogger(__name__)


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
    ]
    can_export = True
    can_view_details = True

    @staticmethod
    def _selected_ids(request: Request) -> list[UUID]:
        raw = request.query_params.get("pks", "")
        return [UUID(value) for value in raw.split(",") if value]

    async def _set_status(self, request: Request, status: TemplateStatus):
        ids = self._selected_ids(request)
        list_url = URL(str(request.url_for("admin:list", identity=self.identity)))
        try:
            async with async_session_factory() as session:
                await TemplateService.set_status(session, ids, status)
        except (RegistryError, ValueError) as exc:
            list_url = list_url.include_query_params(error=str(exc))
        return RedirectResponse(list_url, status_code=302)

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
        list_url = URL(str(request.url_for("admin:list", identity=self.identity)))
        try:
            (
                synced,
                errors,
            ) = await self._admin_ref.app.state.container.template_sync_service.sync_many(
                self._selected_ids(request)
            )
            if errors:
                list_url = list_url.include_query_params(
                    error=f"Synced {synced}; {len(errors)} failed. Check Sync History."
                )
        except (RegistryError, ValueError) as exc:
            list_url = list_url.include_query_params(error=str(exc))
        return RedirectResponse(list_url, status_code=302)

    @action("generate_thumbnail", "Generate Thumbnail", "Generate thumbnails from preview URLs?")
    async def generate_thumbnail(self, request: Request):
        list_url = URL(str(request.url_for("admin:list", identity=self.identity)))
        service = self._admin_ref.app.state.container.screenshot_service
        if not service.enabled:
            return RedirectResponse(
                list_url.include_query_params(error="SCREENSHOT_SERVICE_URL is not configured"),
                status_code=302,
            )
        generated = 0
        async with async_session_factory() as session:
            records = list(
                (
                    await session.scalars(
                        select(Template).where(Template.id.in_(self._selected_ids(request)))
                    )
                ).all()
            )
            for template in records:
                if template.preview_url:
                    url = await service.generate(template.preview_url)
                    if url:
                        template.thumbnail_url = url
                        generated += 1
            await session.commit()
        if generated == 0:
            list_url = list_url.include_query_params(error="No thumbnail was generated")
        return RedirectResponse(list_url, status_code=302)


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


class _ImportBaseView(BaseView):
    async def _choices(self) -> tuple[list[Category], list[Provider]]:
        async with async_session_factory() as session:
            categories = list(
                (await session.scalars(select(Category).where(Category.is_active.is_(True)))).all()
            )
            providers = list(
                (await session.scalars(select(Provider).where(Provider.is_active.is_(True)))).all()
            )
        return categories, providers

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


class GitHubImportView(_ImportBaseView):
    name = "GitHub Import"
    icon = "fa-brands fa-github"

    @expose("/github-import", methods=["GET", "POST"])
    async def github_import(self, request: Request):
        csrf_token = self._csrf(request, "github_import_csrf")
        categories, providers = await self._choices()
        context: dict[str, object] = {
            "title": "Import GitHub Repository",
            "csrf_token": csrf_token,
            "categories": categories,
            "providers": providers,
            "github_authenticated": self._admin_ref.app.state.container.github_authenticated,
        }
        if request.method == "POST":
            form = await request.form()
            try:
                self._validate_csrf(form, csrf_token)
                identity = request.state.admin_identity
                import_service = self._admin_ref.app.state.container.template_import_service
                template = await import_service.import_repository(
                    repository_url=str(form.get("repository_url", "")).strip(),
                    requested_by=identity.subject,
                    adapter_name="github",
                    category_id=UUID(str(form["category_id"])) if form.get("category_id") else None,
                    provider_id=UUID(str(form["provider_id"])) if form.get("provider_id") else None,
                )
                context["success"] = (
                    f"{template.name} imported as draft. Framework: {template.framework.name}; "
                    f"quality score: {template.quality_score}/100."
                )
            except (RegistryError, ValueError) as exc:
                context["error"] = str(exc)
            except Exception:
                logger.exception("Unexpected GitHub import failure")
                context["error"] = "The import failed unexpectedly. Check the application logs."
        return await self.templates.TemplateResponse(request, "github_import.html", context)


class RegistryImportView(_ImportBaseView):
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
            "adapters": [name for name in container.adapter_names if name != "github"],
            "gitlab_authenticated": container.gitlab_authenticated,
            "bitbucket_authenticated": container.bitbucket_authenticated,
        }
        if request.method == "POST":
            form = await request.form()
            try:
                self._validate_csrf(form, csrf_token)
                adapter = str(form.get("adapter", ""))
                identity = request.state.admin_identity
                template = await container.template_import_service.import_repository(
                    repository_url=str(form.get("repository_url", "")).strip(),
                    requested_by=identity.subject,
                    adapter_name=adapter,
                    category_id=UUID(str(form["category_id"])) if form.get("category_id") else None,
                    provider_id=UUID(str(form["provider_id"])) if form.get("provider_id") else None,
                )
                context["success"] = (
                    f"{template.name} imported from {adapter} as draft. "
                    f"Framework: {template.framework.name}."
                )
            except (RegistryError, ValueError) as exc:
                context["error"] = str(exc)
            except Exception:
                logger.exception("Unexpected registry import failure")
                context["error"] = "The import failed unexpectedly. Check the application logs."
        return await self.templates.TemplateResponse(request, "registry_import.html", context)


class LocalImportView(_ImportBaseView):
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
                if not container.local_upload_enabled:
                    raise ValidationError("Local upload is disabled by LOCAL_UPLOAD_ENABLED")
                import_type = str(form.get("import_type", "manifest"))
                if import_type == "manifest":
                    payload = json.loads(str(form.get("manifest_json", "")))
                    if not isinstance(payload, dict):
                        raise ValidationError("Manifest JSON must be an object")
                    imported = repository_from_manifest(payload)
                elif import_type == "zip":
                    upload = form.get("zip_file")
                    if not isinstance(upload, UploadFile) or not upload.filename:
                        raise ValidationError("Select a ZIP file")
                    data = await upload.read(container.local_upload_max_bytes + 1)
                    if len(data) > container.local_upload_max_bytes:
                        raise ValidationError("ZIP exceeds LOCAL_UPLOAD_MAX_BYTES")
                    imported = repository_from_zip(
                        data,
                        upload.filename,
                        max_uncompressed_bytes=container.local_upload_max_uncompressed_bytes,
                        max_entries=container.local_upload_max_entries,
                    )
                else:
                    raise ValidationError("Unsupported local import type")
                identity = request.state.admin_identity
                template = await container.template_import_service.import_imported_repository(
                    imported=imported,
                    requested_by=identity.subject,
                    category_id=UUID(str(form["category_id"])) if form.get("category_id") else None,
                    provider_id=UUID(str(form["provider_id"])) if form.get("provider_id") else None,
                )
                context["success"] = f"{template.name} imported as draft from {import_type}."
            except json.JSONDecodeError:
                context["error"] = "Manifest JSON is invalid"
            except (RegistryError, ValueError) as exc:
                context["error"] = str(exc)
            except Exception:
                logger.exception("Unexpected local import failure")
                context["error"] = "The import failed unexpectedly. Check the application logs."
        return await self.templates.TemplateResponse(request, "local_import.html", context)
