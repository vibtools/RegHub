import math
from datetime import UTC, datetime
from uuid import UUID

from slugify import slugify
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.analyzer.service import TemplateAnalyzer
from app.core.enums import ImportStatus, TemplateStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.integrations.openai.client import AIMetadataEnricher
from app.integrations.screenshot.client import ScreenshotService
from app.models.category import Category
from app.models.framework import Framework
from app.models.import_history import ImportHistory
from app.models.provider import Provider
from app.models.sync_history import SyncHistory
from app.models.template import Template
from app.models.template_asset import TemplateAsset
from app.models.template_version import TemplateVersion
from app.registry.adapters.base import ImportedRepository
from app.registry.adapters.registry import AdapterRegistry
from app.registry.framework import FrameworkService
from app.registry.manifest import build_manifest, validate_manifest
from app.registry.publishing import validate_template_for_publication


class TemplateImportService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        adapters: AdapterRegistry,
        analyzer: TemplateAnalyzer | None = None,
        ai_enricher: AIMetadataEnricher | None = None,
        screenshot_service: ScreenshotService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._adapters = adapters
        self._analyzer = analyzer or TemplateAnalyzer()
        self._ai_enricher = ai_enricher
        self._screenshot_service = screenshot_service

    @property
    def adapter_names(self) -> list[str]:
        return self._adapters.names

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
            template = await self.import_imported_repository(
                imported=imported,
                requested_by=requested_by,
                category_id=category_id,
                provider_id=provider_id,
                history_id=history_id,
            )
            return template
        except Exception as exc:
            await self._mark_failed(history_id, str(exc))
            raise

    async def import_imported_repository(
        self,
        *,
        imported: ImportedRepository,
        requested_by: str,
        category_id: UUID | None = None,
        provider_id: UUID | None = None,
        history_id: UUID | None = None,
    ) -> Template:
        if history_id is None:
            history_id = await self._create_history(
                imported.adapter, imported.repository_url, requested_by
            )
        try:
            analysis = self._analyzer.analyze(imported)
            if self._ai_enricher:
                analysis = await self._ai_enricher.enrich(imported, analysis)
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

                category = await self._resolve_category(
                    session, category_id, analysis.category_slug
                )
                provider = await self._resolve_provider(session, provider_id, imported)
                framework = await FrameworkService.resolve(session, analysis.framework_slug)
                unique_slug = await self._unique_slug(session, analysis.title or imported.name)
                manifest = build_manifest(
                    framework_slug=framework.slug,
                    repository_url=imported.repository_url,
                    default_branch=imported.default_branch,
                    name=analysis.title,
                    analysis=analysis,
                    schema_version="2.0",
                )
                thumbnail = (
                    analysis.screenshots[0]
                    if analysis.screenshots and analysis.screenshots[0].startswith("https://")
                    else None
                )
                preview_url = (
                    imported.homepage_url
                    if imported.homepage_url and imported.homepage_url.startswith("https://")
                    else None
                )
                if not thumbnail and preview_url and self._screenshot_service:
                    thumbnail = await self._screenshot_service.generate(preview_url)
                now = datetime.now(UTC)
                template = Template(
                    name=analysis.title,
                    slug=unique_slug,
                    short_description=analysis.short_description,
                    description=analysis.description,
                    repository_url=imported.repository_url,
                    repository_adapter=imported.adapter,
                    external_repository_id=imported.external_id,
                    default_branch=imported.default_branch,
                    homepage_url=imported.homepage_url,
                    preview_url=preview_url,
                    thumbnail_url=thumbnail,
                    screenshots=analysis.screenshots,
                    license_spdx=imported.license_spdx,
                    primary_language=analysis.language or imported.primary_language,
                    framework_version=analysis.framework_version,
                    package_manager=analysis.package_manager,
                    difficulty=analysis.difficulty,
                    use_case=analysis.use_case,
                    topics=analysis.tags,
                    manifest=manifest.as_dict(),
                    analysis=analysis.to_json(),
                    quality_score=analysis.quality_score,
                    quality_breakdown=analysis.quality_breakdown,
                    stars_count=imported.stars_count,
                    forks_count=imported.forks_count,
                    status=TemplateStatus.DRAFT,
                    last_synced_at=now,
                    source_updated_at=imported.source_updated_at,
                    last_analysis_at=now,
                    created_by=requested_by,
                    category=category,
                    provider=provider,
                    framework=framework,
                )
                session.add(template)
                await session.flush()
                session.add(
                    TemplateVersion(
                        template=template,
                        source_revision=imported.source_revision,
                        metadata_snapshot=imported.metadata,
                        manifest_snapshot=manifest.as_dict(),
                        analysis_snapshot=analysis.to_json(),
                    )
                )
                for order, url in enumerate(analysis.screenshots):
                    session.add(
                        TemplateAsset(
                            template=template,
                            kind="screenshot",
                            url=url,
                            source=imported.adapter,
                            sort_order=order,
                        )
                    )
                history = await session.get(ImportHistory, history_id)
                if history is None:
                    raise RuntimeError("Import history disappeared during import")
                history.status = ImportStatus.SUCCEEDED
                history.template = template
                history.metadata_snapshot = {
                    **imported.metadata,
                    "analysis": analysis.to_json(),
                }
                history.completed_at = now
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

    @classmethod
    async def _resolve_category(
        cls, session: AsyncSession, identifier: UUID | None, inferred_slug: str
    ) -> Category | None:
        selected = await cls._resolve_optional(session, Category, identifier)
        if selected:
            return selected
        category = await session.scalar(
            select(Category).where(Category.slug == inferred_slug, Category.is_active.is_(True))
        )
        if category is None:
            category = await session.scalar(
                select(Category).where(Category.slug == "general", Category.is_active.is_(True))
            )
        return category

    @classmethod
    async def _resolve_provider(
        cls, session: AsyncSession, identifier: UUID | None, imported: ImportedRepository
    ) -> Provider | None:
        selected = await cls._resolve_optional(session, Provider, identifier)
        if selected:
            return selected
        official = any(
            marker in imported.repository_url.casefold()
            for marker in ("github.com/vibtools/", "github.com/ygit/")
        )
        slug = "official" if official else "community"
        provider = await session.scalar(
            select(Provider).where(Provider.slug == slug, Provider.is_active.is_(True))
        )
        return provider

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


class TemplateSyncService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        adapters: AdapterRegistry,
        analyzer: TemplateAnalyzer | None = None,
        ai_enricher: AIMetadataEnricher | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._adapters = adapters
        self._analyzer = analyzer or TemplateAnalyzer()
        self._ai_enricher = ai_enricher

    async def sync_many(self, identifiers: list[UUID]) -> tuple[int, list[str]]:
        synced = 0
        errors: list[str] = []
        for identifier in identifiers:
            try:
                await self.sync_one(identifier)
                synced += 1
            except Exception as exc:
                errors.append(f"{identifier}: {exc}")
        return synced, errors

    async def sync_one(self, identifier: UUID) -> Template:
        async with self._session_factory() as session:
            template = await session.get(Template, identifier)
            if template is None:
                raise NotFoundError("Template not found")
            if template.repository_adapter not in self._adapters.names:
                raise ValidationError(
                    f"Template source {template.repository_adapter} cannot be synchronized"
                )
            history = SyncHistory(
                template=template,
                adapter=template.repository_adapter,
                status=ImportStatus.PENDING,
            )
            session.add(history)
            await session.commit()
            history_id = history.id
            repository_url = template.repository_url
            adapter_name = template.repository_adapter

        try:
            imported = await self._adapters.get(adapter_name).import_repository(repository_url)
            analysis = self._analyzer.analyze(imported)
            if self._ai_enricher:
                analysis = await self._ai_enricher.enrich(imported, analysis)
            async with self._session_factory() as session:
                template = await session.get(Template, identifier)
                history = await session.get(SyncHistory, history_id)
                if template is None or history is None:
                    raise RuntimeError("Template or sync history disappeared during sync")
                framework = await FrameworkService.resolve(session, analysis.framework_slug)
                # Preserve curated identity, classification, publication state, and featured flag.
                template.default_branch = imported.default_branch
                template.homepage_url = imported.homepage_url
                template.preview_url = template.preview_url or imported.homepage_url
                template.license_spdx = imported.license_spdx
                template.primary_language = analysis.language or imported.primary_language
                template.framework_version = analysis.framework_version
                template.package_manager = analysis.package_manager
                template.difficulty = analysis.difficulty
                template.use_case = analysis.use_case
                template.topics = analysis.tags
                template.analysis = analysis.to_json()
                template.quality_score = analysis.quality_score
                template.quality_breakdown = analysis.quality_breakdown
                template.stars_count = imported.stars_count
                template.forks_count = imported.forks_count
                template.screenshots = analysis.screenshots
                template.thumbnail_url = template.thumbnail_url or next(
                    (url for url in analysis.screenshots if url.startswith("https://")), None
                )
                template.framework = framework
                template.manifest = build_manifest(
                    framework_slug=framework.slug,
                    repository_url=imported.repository_url,
                    default_branch=imported.default_branch,
                    name=template.name,
                    analysis=analysis,
                    schema_version="2.0",
                ).as_dict()
                now = datetime.now(UTC)
                template.last_synced_at = now
                template.last_analysis_at = now
                template.source_updated_at = imported.source_updated_at
                session.add(
                    TemplateVersion(
                        template=template,
                        source_revision=imported.source_revision,
                        metadata_snapshot=imported.metadata,
                        manifest_snapshot=template.manifest,
                        analysis_snapshot=analysis.to_json(),
                    )
                )
                await session.execute(
                    TemplateAsset.__table__.delete().where(TemplateAsset.template_id == template.id)
                )
                for order, url in enumerate(analysis.screenshots):
                    session.add(
                        TemplateAsset(
                            template=template,
                            kind="screenshot",
                            url=url,
                            source=imported.adapter,
                            sort_order=order,
                        )
                    )
                history.status = ImportStatus.SUCCEEDED
                history.source_revision = imported.source_revision
                history.metadata_snapshot = imported.metadata
                history.completed_at = now
                await session.commit()
                await session.refresh(template)
                return template
        except Exception as exc:
            async with self._session_factory() as session:
                history = await session.get(SyncHistory, history_id)
                if history:
                    history.status = ImportStatus.FAILED
                    history.error_message = str(exc)[:4000]
                    history.completed_at = datetime.now(UTC)
                    await session.commit()
            raise


class TemplateService:
    @staticmethod
    def _public_query():
        return (
            select(Template)
            .options(
                selectinload(Template.category),
                selectinload(Template.provider),
                selectinload(Template.framework),
            )
            .where(Template.status == TemplateStatus.PUBLISHED)
        )

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
        templates = list(
            (await session.scalars(select(Template).where(Template.id.in_(identifiers)))).all()
        )
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
