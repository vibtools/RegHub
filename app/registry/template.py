import math
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from slugify import slugify
from sqlalchemy import String, and_, asc, cast, desc, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.analyzer.service import TemplateAnalyzer
from app.core.enums import ImportStatus, ScreenshotJobStatus, TemplateStatus
from app.core.exceptions import DuplicateTemplateError, NotFoundError, ValidationError
from app.integrations.openai.client import AIMetadataEnricher
from app.integrations.screenshot.client import ScreenshotService
from app.models.category import Category
from app.models.framework import Framework
from app.models.import_history import ImportHistory
from app.models.provider import Provider
from app.models.screenshot_job import ScreenshotJob
from app.models.sync_history import SyncHistory
from app.models.template import Template
from app.models.template_asset import TemplateAsset
from app.models.template_version import TemplateVersion
from app.registry.adapters.base import ImportedRepository
from app.registry.adapters.registry import AdapterRegistry
from app.registry.framework import FrameworkService
from app.registry.manifest import build_manifest, validate_manifest
from app.registry.provider import ProviderService
from app.registry.publishing import validate_template_for_publication

ProgressCallback = Callable[[int, str, str], Awaitable[None]]


class TemplateImportService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        adapters: AdapterRegistry,
        analyzer: TemplateAnalyzer | None = None,
        ai_enricher: AIMetadataEnricher | None = None,
        screenshot_service: ScreenshotService | None = None,
        provider_auto_create_enabled: bool = True,
    ) -> None:
        self._session_factory = session_factory
        self._adapters = adapters
        self._analyzer = analyzer or TemplateAnalyzer()
        self._ai_enricher = ai_enricher
        self._screenshot_service = screenshot_service
        self._provider_auto_create_enabled = provider_auto_create_enabled

    @staticmethod
    async def _progress(
        callback: ProgressCallback | None, value: int, message: str, level: str = "info"
    ) -> None:
        if callback is not None:
            await callback(value, message, level)

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
        progress: ProgressCallback | None = None,
    ) -> Template:
        repository_url = repository_url.strip()
        await self._progress(
            progress, 5, f"$ reghub import --adapter {adapter_name} --repository {repository_url}"
        )
        await self._progress(progress, 8, "[1/9] Validating repository URL and provider boundary")
        if not repository_url or len(repository_url) > 500:
            raise ValidationError("Repository URL is required and must not exceed 500 characters")
        history_id = await self._create_history(adapter_name, repository_url, requested_by)
        await self._progress(progress, 15, f"[2/9] Import audit record created: {history_id}")
        try:
            await self._progress(
                progress, 20, f"[3/9] Opening authenticated {adapter_name.title()} API client"
            )
            await self._progress(
                progress, 22, f"GET repository metadata from {adapter_name.title()}", "debug"
            )
            imported = await self._adapters.get(adapter_name).import_repository(repository_url)
            await self._progress(progress, 32, f"Repository: {imported.repository_url}", "debug")
            await self._progress(progress, 33, f"External ID: {imported.external_id}", "debug")
            revision = imported.source_revision or "unavailable"
            await self._progress(
                progress,
                34,
                f"Default branch: {imported.default_branch}; revision: {revision}",
                "debug",
            )
            discovery_summary = (
                f"Root entries: {len(imported.root_files)}; "
                f"topics: {len(imported.topics)}; "
                f"screenshots discovered: {len(imported.screenshot_urls)}"
            )
            await self._progress(progress, 35, discovery_summary, "debug")
            await self._progress(progress, 36, "[4/9] Repository metadata received successfully")
            template = await self.import_imported_repository(
                imported=imported,
                requested_by=requested_by,
                category_id=category_id,
                provider_id=provider_id,
                history_id=history_id,
                progress=progress,
            )
            return template
        except DuplicateTemplateError:
            raise
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
        progress: ProgressCallback | None = None,
    ) -> Template:
        if history_id is None:
            history_id = await self._create_history(
                imported.adapter, imported.repository_url, requested_by
            )
        try:
            await self._progress(
                progress, 42, "[5/9] Analyzing repository files, manifests and package metadata"
            )
            analysis = self._analyzer.analyze(imported)
            package_manager = analysis.package_manager or "unknown"
            language = analysis.language or imported.primary_language or "unknown"
            await self._progress(
                progress,
                48,
                f"package_manager={package_manager} language={language}",
                "debug",
            )
            framework_version = analysis.framework_version or "unknown"
            confidence = analysis.evidence.get("confidence", "unknown")
            await self._progress(
                progress,
                50,
                (
                    f"framework={analysis.framework_slug} "
                    f"version={framework_version} confidence={confidence}"
                ),
                "debug",
            )
            await self._progress(progress, 52, f"Framework detected: {analysis.framework_name}")
            if self._ai_enricher and self._ai_enricher.enabled:
                await self._progress(progress, 56, "Running optional AI metadata enrichment")
                analysis = await self._ai_enricher.enrich(imported, analysis)
                await self._progress(progress, 60, "AI metadata enrichment completed")
            else:
                await self._progress(
                    progress,
                    60,
                    "AI metadata enrichment is disabled; deterministic metadata retained",
                    "debug",
                )
            async with self._session_factory() as session:
                await self._progress(
                    progress,
                    64,
                    "[6/9] Checking duplicates and resolving category/provider/framework",
                )
                duplicate = await session.scalar(
                    select(Template).where(
                        or_(
                            Template.repository_url == imported.repository_url,
                            Template.external_repository_id == imported.external_id,
                        )
                    )
                )
                if duplicate:
                    duplicate_message = (
                        f"Repository already registered as template "
                        f"'{duplicate.name}' ({duplicate.slug})"
                    )
                    await self._progress(
                        progress,
                        68,
                        duplicate_message,
                        "notice",
                    )
                    await self._mark_duplicate(history_id, duplicate)
                    raise DuplicateTemplateError(
                        "This repository is already registered in RegHub",
                        template_id=duplicate.id,
                        template_slug=duplicate.slug,
                        template_name=duplicate.name,
                    )

                category = await self._resolve_category(
                    session, category_id, analysis.category_slug
                )
                provider = await self._resolve_provider(session, provider_id, imported)
                framework = await FrameworkService.resolve(session, analysis.framework_slug)
                unique_slug = await self._unique_slug(session, analysis.title or imported.name)
                category_slug = category.slug if category else "none"
                provider_slug = provider.slug if provider else "none"
                resolved_resources = (
                    f"category={category_slug} provider={provider_slug} framework={framework.slug}"
                )
                await self._progress(progress, 69, resolved_resources, "debug")
                await self._progress(progress, 72, "[7/9] Building Manifest v2 and media metadata")
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
                generated_thumbnail = False
                if not thumbnail and preview_url and self._screenshot_service:
                    thumbnail = await self._screenshot_service.generate(preview_url)
                    generated_thumbnail = bool(thumbnail)
                all_screenshots = list(analysis.screenshots)
                if generated_thumbnail and thumbnail and thumbnail not in all_screenshots:
                    all_screenshots.insert(0, thumbnail)
                all_screenshots = all_screenshots[:20]
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
                    screenshots=all_screenshots,
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
                await self._progress(
                    progress,
                    82,
                    "[8/9] BEGIN database transaction: template + version + sync history + assets",
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
                session.add(
                    SyncHistory(
                        template=template,
                        adapter=imported.adapter,
                        trigger="initial_import",
                        requested_by=requested_by,
                        status=ImportStatus.SUCCEEDED,
                        source_revision=imported.source_revision,
                        metadata_snapshot=imported.metadata,
                        changes={"created": True, "asset_count": len(all_screenshots)},
                        completed_at=now,
                    )
                )
                for order, url in enumerate(all_screenshots):
                    is_generated = generated_thumbnail and url == thumbnail
                    session.add(
                        TemplateAsset(
                            template=template,
                            kind="thumbnail" if is_generated else "screenshot",
                            url=url,
                            source="screenshot-service" if is_generated else imported.adapter,
                            sort_order=order,
                        )
                    )
                if generated_thumbnail and thumbnail and preview_url:
                    session.add(
                        ScreenshotJob(
                            template=template,
                            status=ScreenshotJobStatus.SUCCEEDED,
                            preview_url=preview_url,
                            screenshot_url=thumbnail,
                            attempts=1,
                            requested_by=requested_by,
                            response_metadata={"trigger": "initial_import"},
                            completed_at=now,
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
                await self._progress(
                    progress, 92, f"COMMIT database transaction; template_id={template.id}", "debug"
                )
                await self._progress(progress, 94, "[9/9] Template import transaction committed")
                return template
        except DuplicateTemplateError:
            raise
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

    async def _mark_duplicate(self, history_id: UUID, template: Template) -> None:
        async with self._session_factory() as session:
            history = await session.get(ImportHistory, history_id)
            if history:
                history.status = ImportStatus.SUCCEEDED
                history.template_id = template.id
                history.error_message = None
                history.metadata_snapshot = {
                    "outcome": "already_exists",
                    "template_id": str(template.id),
                    "template_slug": template.slug,
                    "template_name": template.name,
                }
                history.completed_at = datetime.now(UTC)
                await session.commit()

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

    async def _resolve_provider(
        self, session: AsyncSession, identifier: UUID | None, imported: ImportedRepository
    ) -> Provider | None:
        selected = await self._resolve_optional(session, Provider, identifier)
        if selected:
            return selected
        if self._provider_auto_create_enabled:
            return await ProviderService.resolve_for_repository(session, imported)
        return await session.scalar(
            select(Provider).where(Provider.slug == "community", Provider.is_active.is_(True))
        )

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
        screenshot_service: ScreenshotService | None = None,
        provider_auto_create_enabled: bool = True,
    ) -> None:
        self._session_factory = session_factory
        self._adapters = adapters
        self._analyzer = analyzer or TemplateAnalyzer()
        self._ai_enricher = ai_enricher
        self._screenshot_service = screenshot_service
        self._provider_auto_create_enabled = provider_auto_create_enabled

    @staticmethod
    async def _progress(
        callback: ProgressCallback | None, value: int, message: str, level: str = "info"
    ) -> None:
        if callback is not None:
            await callback(value, message, level)

    async def sync_many(
        self,
        identifiers: list[UUID],
        *,
        requested_by: str | None = None,
        progress: ProgressCallback | None = None,
    ) -> tuple[int, list[str]]:
        if not identifiers:
            raise ValidationError("No templates were selected")
        synced = 0
        errors: list[str] = []
        for identifier in identifiers:
            try:
                await self.sync_one(identifier, requested_by=requested_by, progress=progress)
                synced += 1
            except Exception as exc:
                errors.append(f"{identifier}: {exc}")
        return synced, errors

    @staticmethod
    def _changes(
        template: Template, imported: ImportedRepository, analysis: object
    ) -> dict[str, object]:
        tracked = {
            "default_branch": (template.default_branch, imported.default_branch),
            "homepage_url": (template.homepage_url, imported.homepage_url),
            "license_spdx": (template.license_spdx, imported.license_spdx),
            "framework_version": (template.framework_version, analysis.framework_version),
            "language": (template.primary_language, analysis.language or imported.primary_language),
            "quality_score": (template.quality_score, analysis.quality_score),
            "stars_count": (template.stars_count, imported.stars_count),
            "forks_count": (template.forks_count, imported.forks_count),
            "screenshot_count": (len(template.screenshots), len(analysis.screenshots)),
        }
        return {
            key: {"before": before, "after": after}
            for key, (before, after) in tracked.items()
            if before != after
        }

    async def sync_one(
        self,
        identifier: UUID,
        *,
        requested_by: str | None = None,
        progress: ProgressCallback | None = None,
    ) -> Template:
        await self._progress(progress, 8, "Loading template and creating sync history")
        async with self._session_factory() as session:
            template = await session.get(Template, identifier)
            if template is None:
                raise NotFoundError("Template not found")
            history = SyncHistory(
                template=template,
                adapter=template.repository_adapter,
                trigger="manual",
                requested_by=requested_by,
                status=ImportStatus.PENDING,
            )
            session.add(history)
            await session.commit()
            history_id = history.id
            repository_url = template.repository_url
            adapter_name = template.repository_adapter

        try:
            if adapter_name not in self._adapters.names:
                raise ValidationError(f"Template source {adapter_name} cannot be synchronized")
            await self._progress(
                progress, 20, f"Fetching latest metadata from {adapter_name.title()}"
            )
            imported = await self._adapters.get(adapter_name).import_repository(repository_url)
            await self._progress(progress, 38, "Analyzing latest repository metadata")
            analysis = self._analyzer.analyze(imported)
            await self._progress(progress, 48, f"Framework detected: {analysis.framework_name}")
            if self._ai_enricher and self._ai_enricher.enabled:
                await self._progress(progress, 52, "Running optional AI metadata enrichment")
                analysis = await self._ai_enricher.enrich(imported, analysis)
            await self._progress(
                progress, 58, "Applying source updates while preserving curated fields"
            )
            async with self._session_factory() as session:
                template = await session.get(Template, identifier)
                history = await session.get(SyncHistory, history_id)
                if template is None or history is None:
                    raise RuntimeError("Template or sync history disappeared during sync")
                framework = await FrameworkService.resolve(session, analysis.framework_slug)
                changes = self._changes(template, imported, analysis)
                # Preserve curated identity, category, publication state, and featured flag.
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
                preserved_assets = list(
                    (
                        await session.scalars(
                            select(TemplateAsset)
                            .where(
                                TemplateAsset.template_id == template.id,
                                TemplateAsset.source.in_(["manual", "screenshot-service"]),
                            )
                            .order_by(TemplateAsset.sort_order, TemplateAsset.created_at)
                        )
                    ).all()
                )
                preserved_urls = [
                    asset.url
                    for asset in preserved_assets
                    if asset.kind in {"screenshot", "image", "thumbnail"}
                ]
                combined_screenshots = list(
                    dict.fromkeys([*preserved_urls, *analysis.screenshots])
                )[:20]
                changes["screenshot_count"] = {
                    "before": len(template.screenshots),
                    "after": len(combined_screenshots),
                }
                if changes["screenshot_count"]["before"] == changes["screenshot_count"]["after"]:
                    changes.pop("screenshot_count")
                template.screenshots = combined_screenshots
                template.thumbnail_url = template.thumbnail_url or next(
                    (url for url in combined_screenshots if url.startswith("https://")), None
                )
                template.framework = framework
                if self._provider_auto_create_enabled and (
                    template.provider is None or template.provider.slug == "community"
                ):
                    template.provider = await ProviderService.resolve_for_repository(
                        session, imported
                    )
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
                # Preserve manually curated assets; replace only source-discovered assets.
                await session.execute(
                    TemplateAsset.__table__.delete().where(
                        TemplateAsset.template_id == template.id,
                        TemplateAsset.source != "manual",
                        TemplateAsset.source != "screenshot-service",
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
                history.status = ImportStatus.SUCCEEDED
                history.source_revision = imported.source_revision
                history.metadata_snapshot = imported.metadata
                history.changes = changes
                history.completed_at = now
                await self._progress(
                    progress, 88, "Committing sync history, assets and version snapshot"
                )
                await session.commit()
                await session.refresh(template)
                await self._progress(progress, 96, "Source synchronization completed")
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
        tag: str | None = None,
        language: str | None = None,
        difficulty: str | None = None,
        use_case: str | None = None,
        min_quality: int | None = None,
        updated_since: datetime | None = None,
        sort: str = "featured",
        order: str = "desc",
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
        if tag:
            normalized_tag = tag.strip().casefold()
            bind = session.get_bind()
            if bind.dialect.name == "postgresql":
                filters.append(Template.topics.op("@>")(cast([normalized_tag], JSONB)))
            else:
                escaped = (
                    normalized_tag.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                )
                filters.append(cast(Template.topics, String).ilike(f'%"{escaped}"%', escape="\\"))
        if language:
            filters.append(func.lower(Template.primary_language) == language.casefold())
        if difficulty:
            filters.append(func.lower(Template.difficulty) == difficulty.casefold())
        if use_case:
            filters.append(func.lower(Template.use_case) == use_case.casefold())
        if min_quality is not None:
            filters.append(Template.quality_score >= min_quality)
        if updated_since is not None:
            filters.append(Template.updated_at >= updated_since)

        query = cls._public_query().where(*filters)
        count_query = select(func.count(Template.id)).where(
            Template.status == TemplateStatus.PUBLISHED, *filters
        )
        total = int(await session.scalar(count_query) or 0)
        sort_columns = {
            "featured": Template.is_featured,
            "newest": Template.published_at,
            "updated": Template.updated_at,
            "quality": Template.quality_score,
            "stars": Template.stars_count,
            "name": Template.name,
        }
        sort_column = sort_columns.get(sort, Template.is_featured)
        direction = asc if order == "asc" else desc
        ordering = [direction(sort_column)]
        if sort == "featured":
            ordering.append(Template.published_at.desc())
        ordering.append(Template.id.asc())
        records = list(
            (
                await session.scalars(
                    query.order_by(*ordering).offset((page - 1) * page_size).limit(page_size)
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

    @classmethod
    async def public_facets(cls, session: AsyncSession) -> dict[str, list[dict[str, object]]]:
        async def relation_counts(model: type, foreign_key: object) -> list[dict[str, object]]:
            rows = (
                await session.execute(
                    select(model.name, model.slug, func.count(Template.id))
                    .select_from(model)
                    .outerjoin(
                        Template,
                        and_(
                            foreign_key == model.id,
                            Template.status == TemplateStatus.PUBLISHED,
                        ),
                    )
                    .where(model.is_active.is_(True))
                    .group_by(model.id, model.name, model.slug)
                    .order_by(func.count(Template.id).desc(), model.name)
                )
            ).all()
            return [
                {"name": str(name), "slug": str(slug), "count": int(count)}
                for name, slug, count in rows
            ]

        categories = await relation_counts(Category, Template.category_id)
        providers = await relation_counts(Provider, Template.provider_id)
        frameworks = await relation_counts(Framework, Template.framework_id)
        status_filter = Template.status == TemplateStatus.PUBLISHED
        language_rows = (
            await session.execute(
                select(Template.primary_language, func.count(Template.id))
                .where(status_filter, Template.primary_language.is_not(None))
                .group_by(Template.primary_language)
                .order_by(func.count(Template.id).desc(), Template.primary_language)
            )
        ).all()
        difficulty_rows = (
            await session.execute(
                select(Template.difficulty, func.count(Template.id))
                .where(status_filter, Template.difficulty.is_not(None))
                .group_by(Template.difficulty)
                .order_by(func.count(Template.id).desc(), Template.difficulty)
            )
        ).all()
        return {
            "categories": categories,
            "providers": providers,
            "frameworks": frameworks,
            "languages": [
                {"name": str(name), "slug": slugify(str(name)), "count": int(count)}
                for name, count in language_rows
            ],
            "difficulties": [
                {"name": str(name).title(), "slug": str(name).casefold(), "count": int(count)}
                for name, count in difficulty_rows
            ],
        }

    @classmethod
    async def list_public_assets(cls, session: AsyncSession, slug: str) -> list[TemplateAsset]:
        template = await cls.get_public_by_slug(session, slug)
        return list(
            (
                await session.scalars(
                    select(TemplateAsset)
                    .where(TemplateAsset.template_id == template.id)
                    .order_by(TemplateAsset.sort_order, TemplateAsset.created_at)
                )
            ).all()
        )

    @classmethod
    async def public_freshness(cls, session: AsyncSession, slug: str) -> dict[str, object]:
        template = await cls.get_public_by_slug(session, slug)
        latest_sync = await session.scalar(
            select(SyncHistory)
            .where(
                SyncHistory.template_id == template.id,
                SyncHistory.status == ImportStatus.SUCCEEDED,
            )
            .order_by(SyncHistory.completed_at.desc())
            .limit(1)
        )
        return {
            "template_id": template.id,
            "slug": template.slug,
            "updated_at": template.updated_at,
            "source_updated_at": template.source_updated_at,
            "last_synced_at": template.last_synced_at,
            "last_analysis_at": template.last_analysis_at,
            "source_revision": latest_sync.source_revision if latest_sync else None,
            "sync_status": latest_sync.status.value if latest_sync else None,
            "is_stale": bool(
                template.source_updated_at
                and template.last_synced_at
                and template.source_updated_at > template.last_synced_at
            ),
        }

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
