from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.enums import ScreenshotJobStatus
from app.core.exceptions import NotFoundError, ValidationError
from app.core.url_security import validate_public_https_url
from app.integrations.screenshot.client import ScreenshotService
from app.models.screenshot_job import ScreenshotJob
from app.models.template import Template
from app.models.template_asset import TemplateAsset


class TemplateAssetService:
    _KINDS: ClassVar[set[str]] = {"screenshot", "thumbnail", "preview", "image"}

    @staticmethod
    async def list_for_template(session: AsyncSession, template_id: UUID) -> list[TemplateAsset]:
        return list(
            (
                await session.scalars(
                    select(TemplateAsset)
                    .where(TemplateAsset.template_id == template_id)
                    .order_by(TemplateAsset.sort_order, TemplateAsset.created_at)
                )
            ).all()
        )

    @classmethod
    def _normalize_kind(cls, kind: str) -> str:
        normalized = kind.strip().casefold()
        if normalized not in cls._KINDS:
            raise ValidationError("Unsupported asset kind")
        return normalized

    @staticmethod
    async def _sync_template_media(session: AsyncSession, template: Template) -> None:
        assets = list(
            (
                await session.scalars(
                    select(TemplateAsset)
                    .where(TemplateAsset.template_id == template.id)
                    .order_by(TemplateAsset.sort_order, TemplateAsset.created_at)
                )
            ).all()
        )
        screenshots = [item.url for item in assets if item.kind in {"screenshot", "image"}][:20]
        template.screenshots = screenshots
        template.preview_url = next(
            (item.url for item in assets if item.kind == "preview"),
            template.preview_url if not any(item.kind == "preview" for item in assets) else None,
        )
        explicit_thumbnail = next((item.url for item in assets if item.kind == "thumbnail"), None)
        template.thumbnail_url = explicit_thumbnail or (screenshots[0] if screenshots else None)

    @classmethod
    async def add_manual(
        cls,
        session: AsyncSession,
        *,
        template_id: UUID,
        url: str,
        kind: str = "screenshot",
        sort_order: int = 0,
    ) -> TemplateAsset:
        template = await session.get(Template, template_id)
        if template is None:
            raise NotFoundError("Template not found")
        validated = validate_public_https_url(url, field_name="Asset URL")
        normalized_kind = cls._normalize_kind(kind)
        duplicate = await session.scalar(
            select(TemplateAsset).where(
                TemplateAsset.template_id == template_id,
                TemplateAsset.url == validated,
            )
        )
        if duplicate:
            duplicate.kind = normalized_kind
            duplicate.source = "manual"
            duplicate.sort_order = max(0, min(sort_order, 10_000))
            await session.flush()
            await cls._sync_template_media(session, template)
            await session.commit()
            await session.refresh(duplicate)
            return duplicate
        asset = TemplateAsset(
            template=template,
            kind=normalized_kind,
            url=validated,
            source="manual",
            sort_order=max(0, min(sort_order, 10_000)),
        )
        session.add(asset)
        await session.flush()
        await cls._sync_template_media(session, template)
        await session.commit()
        await session.refresh(asset)
        return asset

    @classmethod
    async def update_manual(
        cls,
        session: AsyncSession,
        *,
        asset_id: UUID,
        url: str,
        kind: str,
        sort_order: int,
    ) -> TemplateAsset:
        asset = await session.get(TemplateAsset, asset_id)
        if asset is None:
            raise NotFoundError("Asset not found")
        validated = validate_public_https_url(url, field_name="Asset URL")
        normalized_kind = cls._normalize_kind(kind)
        duplicate = await session.scalar(
            select(TemplateAsset).where(
                TemplateAsset.template_id == asset.template_id,
                TemplateAsset.url == validated,
                TemplateAsset.id != asset.id,
            )
        )
        if duplicate is not None:
            raise ValidationError("This asset URL is already attached to the template")
        old_url = asset.url
        old_kind = asset.kind
        asset.url = validated
        asset.kind = normalized_kind
        asset.source = "manual"
        asset.sort_order = max(0, min(sort_order, 10_000))
        template = await session.get(Template, asset.template_id)
        if template:
            if old_kind == "preview" and template.preview_url == old_url:
                template.preview_url = None
            await session.flush()
            await cls._sync_template_media(session, template)
        await session.commit()
        await session.refresh(asset)
        return asset

    @classmethod
    async def delete_manual(cls, session: AsyncSession, asset_id: UUID) -> None:
        asset = await session.get(TemplateAsset, asset_id)
        if asset is None:
            raise NotFoundError("Asset not found")
        template = await session.get(Template, asset.template_id)
        await session.delete(asset)
        await session.flush()
        if template:
            # If the deleted record supplied the preview, clear it before rebuilding from assets.
            if asset.kind == "preview" and template.preview_url == asset.url:
                template.preview_url = None
            await cls._sync_template_media(session, template)
        await session.commit()


class ScreenshotJobService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        screenshot_service: ScreenshotService,
    ) -> None:
        self._session_factory = session_factory
        self._service = screenshot_service

    @property
    def enabled(self) -> bool:
        return self._service.enabled

    async def create_and_run(self, template_id: UUID, requested_by: str | None) -> ScreenshotJob:
        async with self._session_factory() as session:
            template = await session.get(Template, template_id)
            if template is None:
                raise NotFoundError("Template not found")
            if not template.preview_url:
                raise ValidationError("Template has no preview URL")
            preview_url = validate_public_https_url(template.preview_url, field_name="Preview URL")
            job = ScreenshotJob(
                template=template,
                status=ScreenshotJobStatus.PENDING,
                preview_url=preview_url,
                requested_by=requested_by,
            )
            session.add(job)
            await session.commit()
            job_id = job.id

        try:
            async with self._session_factory() as session:
                job = await session.get(ScreenshotJob, job_id)
                if job is None:
                    raise RuntimeError("Screenshot job disappeared")
                job.status = ScreenshotJobStatus.RUNNING
                job.attempts += 1
                await session.commit()
            screenshot_url, metadata = await self._service.generate_with_metadata(preview_url)
            async with self._session_factory() as session:
                job = await session.get(ScreenshotJob, job_id)
                template = await session.get(Template, template_id)
                if job is None or template is None:
                    raise RuntimeError("Screenshot job or template disappeared")
                job.status = ScreenshotJobStatus.SUCCEEDED
                job.screenshot_url = screenshot_url
                job.response_metadata = metadata
                job.completed_at = datetime.now(UTC)
                template.thumbnail_url = screenshot_url
                if screenshot_url not in template.screenshots:
                    template.screenshots = [screenshot_url, *template.screenshots][:20]
                existing = await session.scalar(
                    select(TemplateAsset).where(
                        TemplateAsset.template_id == template_id,
                        TemplateAsset.url == screenshot_url,
                    )
                )
                if existing is None:
                    session.add(
                        TemplateAsset(
                            template=template,
                            kind="thumbnail",
                            url=screenshot_url,
                            source="screenshot-service",
                            sort_order=0,
                        )
                    )
                await session.commit()
                await session.refresh(job)
                return job
        except Exception as exc:
            async with self._session_factory() as session:
                job = await session.get(ScreenshotJob, job_id)
                if job:
                    job.status = ScreenshotJobStatus.FAILED
                    job.error_message = str(exc)[:4000]
                    job.completed_at = datetime.now(UTC)
                    await session.commit()
            raise

    async def retry(self, job_id: UUID, requested_by: str | None) -> ScreenshotJob:
        async with self._session_factory() as session:
            job = await session.get(ScreenshotJob, job_id)
            if job is None:
                raise NotFoundError("Screenshot job not found")
            template_id = job.template_id
        return await self.create_and_run(template_id, requested_by)
