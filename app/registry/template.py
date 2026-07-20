import math
from datetime import UTC, datetime
from uuid import UUID

from slugify import slugify
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.enums import ImportStatus, TemplateStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.category import Category
from app.models.framework import Framework
from app.models.import_history import ImportHistory
from app.models.provider import Provider
from app.models.template import Template
from app.registry.adapters.registry import AdapterRegistry
from app.registry.framework import FrameworkService
from app.registry.manifest import build_manifest, validate_manifest
from app.registry.publishing import validate_template_for_publication


class TemplateImportService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        adapters: AdapterRegistry,
    ) -> None:
        self._session_factory = session_factory
        self._adapters = adapters

    async def import_repository(
        self,
        *,
        repository_url: str,
        requested_by: str,
        adapter_name: str = "github",
        category_id: UUID | None = None,
        provider_id: UUID | None = None,
    ) -> Template:
        repository_url = repository_url.strip()
        if not repository_url or len(repository_url) > 500:
            raise ValidationError("Repository URL is required and must not exceed 500 characters")
        history_id = await self._create_history(adapter_name, repository_url, requested_by)
        try:
            imported = await self._adapters.get(adapter_name).import_repository(repository_url)
            async with self._session_factory() as session:
                duplicate = await session.scalar(
                    select(Template).where(
                        or_(
                            Template.repository_url == imported.repository_url,
                            Template.external_repository_id == imported.external_id,
                        )
                    )
                )
                if duplicate:
                    raise ConflictError("This repository already exists in RegHub")

                category = await self._resolve_optional(session, Category, category_id)
                provider = await self._resolve_optional(session, Provider, provider_id)
                framework_slug = FrameworkService.detect_slug(imported)
                framework = await FrameworkService.resolve(session, framework_slug)
                unique_slug = await self._unique_slug(session, imported.name)
                manifest = build_manifest(
                    framework_slug=framework.slug,
                    repository_url=imported.repository_url,
                    default_branch=imported.default_branch,
                )
                template = Template(
                    name=imported.name.replace("-", " ").replace("_", " ").title(),
                    slug=unique_slug,
                    short_description=imported.description[:320] if imported.description else None,
                    description=imported.description,
                    repository_url=imported.repository_url,
                    repository_adapter=imported.adapter,
                    external_repository_id=imported.external_id,
                    default_branch=imported.default_branch,
                    homepage_url=imported.homepage_url,
                    license_spdx=imported.license_spdx,
                    primary_language=imported.primary_language,
                    topics=imported.topics,
                    manifest=manifest.model_dump(mode="json"),
                    stars_count=imported.stars_count,
                    forks_count=imported.forks_count,
                    status=TemplateStatus.DRAFT,
                    last_synced_at=datetime.now(UTC),
                    created_by=requested_by,
                    category=category,
                    provider=provider,
                    framework=framework,
                )
                session.add(template)
                history = await session.get(ImportHistory, history_id)
                if history is None:
                    raise RuntimeError("Import history disappeared during import")
                history.status = ImportStatus.SUCCEEDED
                history.template = template
                history.metadata_snapshot = imported.metadata
                history.completed_at = datetime.now(UTC)
                await session.commit()
                await session.refresh(template)
                return template
        except Exception as exc:
            await self._mark_failed(history_id, str(exc))
            raise

    async def _create_history(self, adapter: str, url: str, requested_by: str) -> UUID:
        async with self._session_factory() as session:
            history = ImportHistory(
                adapter=adapter,
                repository_url=url,
                status=ImportStatus.PENDING,
                requested_by=requested_by,
            )
            session.add(history)
            await session.commit()
            return history.id

    async def _mark_failed(self, history_id: UUID, message: str) -> None:
        async with self._session_factory() as session:
            history = await session.get(ImportHistory, history_id)
            if history:
                history.status = ImportStatus.FAILED
                history.error_message = message[:4000]
                history.completed_at = datetime.now(UTC)
                await session.commit()

    @staticmethod
    async def _resolve_optional(session: AsyncSession, model: type, identifier: UUID | None):
        if identifier is None:
            return None
        value = await session.get(model, identifier)
        if value is None:
            raise ValidationError(f"Selected {model.__name__.lower()} does not exist")
        return value

    @staticmethod
    async def _unique_slug(session: AsyncSession, name: str) -> str:
        base = slugify(name)[:160] or "template"
        candidate = base
        counter = 2
        while await session.scalar(select(Template.id).where(Template.slug == candidate)):
            suffix = f"-{counter}"
            candidate = f"{base[: 180 - len(suffix)]}{suffix}"
            counter += 1
        return candidate


class TemplateService:
    @staticmethod
    def _public_query():
        return select(Template).options(
            selectinload(Template.category),
            selectinload(Template.provider),
            selectinload(Template.framework),
        ).where(Template.status == TemplateStatus.PUBLISHED)

    @classmethod
    async def list_public(
        cls,
        session: AsyncSession,
        *,
        page: int,
        page_size: int,
        search: str | None,
        category: str | None,
        provider: str | None,
        framework: str | None,
        featured: bool | None,
    ) -> tuple[list[Template], int, int]:
        filters = []
        if search:
            term = search.strip()
            filters.append(
                or_(
                    Template.name.icontains(term, autoescape=True),
                    Template.short_description.icontains(term, autoescape=True),
                )
            )
        if category:
            filters.append(Template.category.has(Category.slug == category))
        if provider:
            filters.append(Template.provider.has(Provider.slug == provider))
        if framework:
            filters.append(Template.framework.has(Framework.slug == framework))
        if featured is not None:
            filters.append(Template.is_featured.is_(featured))

        query = cls._public_query().where(*filters)
        count_query = select(func.count(Template.id)).where(
            Template.status == TemplateStatus.PUBLISHED, *filters
        )
        total = int(await session.scalar(count_query) or 0)
        records = list(
            (
                await session.scalars(
                    query.order_by(Template.is_featured.desc(), Template.published_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).unique()
        )
        return records, total, max(1, math.ceil(total / page_size)) if total else 0

    @classmethod
    async def get_public_by_slug(cls, session: AsyncSession, slug: str) -> Template:
        template = await session.scalar(cls._public_query().where(Template.slug == slug))
        if template is None:
            raise NotFoundError("Published template not found")
        validate_manifest(template.manifest)
        return template

    @staticmethod
    async def set_status(
        session: AsyncSession, identifiers: list[UUID], status: TemplateStatus
    ) -> int:
        templates = list((await session.scalars(select(Template).where(Template.id.in_(identifiers)))).all())
        if not templates:
            raise NotFoundError("No templates were selected")
        for template in templates:
            if status == TemplateStatus.PUBLISHED:
                validate_template_for_publication(template)
                template.published_at = template.published_at or datetime.now(UTC)
            elif template.status == TemplateStatus.PUBLISHED:
                template.published_at = None
            template.status = status
        await session.commit()
        return len(templates)
