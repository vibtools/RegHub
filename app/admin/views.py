import logging
import secrets
from hmac import compare_digest
from uuid import UUID

from sqladmin import BaseView, ModelView, action, expose
from sqlalchemy import select
from starlette.requests import Request
from starlette.datastructures import URL
from starlette.responses import RedirectResponse

from app.core.enums import TemplateStatus
from app.core.exceptions import RegistryError

logger = logging.getLogger(__name__)
from app.database.session import async_session_factory
from app.models.category import Category
from app.models.framework import Framework
from app.models.import_history import ImportHistory
from app.models.provider import Provider
from app.models.template import Template
from app.registry.template import TemplateService


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
        Template.provider,
        Template.category,
        Template.is_featured,
        Template.updated_at,
    ]
    column_searchable_list = [Template.name, Template.slug, Template.repository_url]
    column_sortable_list = [Template.name, Template.status, Template.stars_count, Template.updated_at]
    column_filters = [Template.status, Template.is_featured, Template.framework_id]
    form_excluded_columns = [
        Template.created_at,
        Template.updated_at,
        Template.status,
        Template.published_at,
        Template.last_synced_at,
        Template.external_repository_id,
        Template.repository_adapter,
        Template.stars_count,
        Template.forks_count,
        Template.created_by,
    ]
    can_export = True
    can_view_details = True

    async def _set_status(self, request: Request, status: TemplateStatus):
        raw = request.query_params.get("pks", "")
        ids = [UUID(value) for value in raw.split(",") if value]
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


class GitHubImportView(BaseView):
    name = "GitHub Import"
    icon = "fa-brands fa-github"

    @expose("/github-import", methods=["GET", "POST"])
    async def github_import(self, request: Request):
        csrf_token = request.session.get("github_import_csrf")
        if not isinstance(csrf_token, str):
            csrf_token = secrets.token_urlsafe(32)
            request.session["github_import_csrf"] = csrf_token
        context: dict[str, object] = {
            "title": "Import GitHub Repository",
            "csrf_token": csrf_token,
        }
        async with async_session_factory() as session:
            context["categories"] = list(
                (await session.scalars(select(Category).where(Category.is_active.is_(True)))).all()
            )
            context["providers"] = list(
                (await session.scalars(select(Provider).where(Provider.is_active.is_(True)))).all()
            )

        if request.method == "POST":
            form = await request.form()
            submitted_csrf = str(form.get("csrf_token", ""))
            if not submitted_csrf or not compare_digest(submitted_csrf, csrf_token):
                context["error"] = "The form session expired. Reload the page and try again."
                return await self.templates.TemplateResponse(request, "github_import.html", context, status_code=400)
            repository_url = str(form.get("repository_url", "")).strip()
            category_raw = str(form.get("category_id", "")).strip()
            provider_raw = str(form.get("provider_id", "")).strip()
            identity = request.state.admin_identity
            try:
                template = await self._admin_ref.app.state.container.template_import_service.import_repository(
                    repository_url=repository_url,
                    requested_by=identity.subject,
                    category_id=UUID(category_raw) if category_raw else None,
                    provider_id=UUID(provider_raw) if provider_raw else None,
                )
                context["success"] = f"{template.name} was imported as a draft."
                csrf_token = secrets.token_urlsafe(32)
                request.session["github_import_csrf"] = csrf_token
                context["csrf_token"] = csrf_token
            except (RegistryError, ValueError) as exc:
                context["error"] = str(exc)
            except Exception:
                logger.exception("Unexpected GitHub import failure")
                context["error"] = "The import failed unexpectedly. Check the application logs."
        return await self.templates.TemplateResponse(request, "github_import.html", context)
