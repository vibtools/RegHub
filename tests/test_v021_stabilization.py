from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.analyzer.media import extract_readme_image_references, is_probable_template_image
from app.core.enums import ImportStatus, ScreenshotJobStatus, TemplateStatus
from app.core.exceptions import ValidationError
from app.core.url_security import validate_public_https_url
from app.database.base import Base
from app.models.category import Category
from app.models.framework import Framework
from app.models.provider import Provider
from app.models.screenshot_job import ScreenshotJob
from app.models.sync_history import SyncHistory
from app.models.template import Template
from app.models.template_asset import TemplateAsset
from app.registry.adapters.base import ImportedRepository, RegistryAdapter
from app.registry.adapters.registry import AdapterRegistry
from app.registry.media import ScreenshotJobService, TemplateAssetService
from app.registry.template import TemplateImportService, TemplateService, TemplateSyncService


class OwnerAdapter(RegistryAdapter):
    name = "github"

    async def import_repository(self, repository_url: str) -> ImportedRepository:
        return ImportedRepository(
            adapter="github",
            external_id="owner-repo-1",
            name="owner-template",
            description="A template",
            repository_url=repository_url,
            default_branch="main",
            homepage_url="https://preview.example.com",
            license_spdx="MIT",
            topics=["astro", "portfolio"],
            primary_language="TypeScript",
            stars_count=25,
            forks_count=3,
            root_files=frozenset({"package.json", "astro.config.mjs"}),
            package_json={"dependencies": {"astro": "5.0.0"}},
            metadata={"owner": "Acme"},
            source_revision="abc123",
            source_updated_at=datetime.now(UTC),
            readme_text="# Preview\n![Screenshot](docs/preview.png)",
            screenshot_urls=["https://cdn.example.com/preview.png"],
            owner_login="acme",
            owner_name="Acme Studio",
            owner_type="Organization",
            owner_url="https://github.com/acme",
        )


async def _database(tmp_path, name: str):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / name}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        session.add_all(
            [
                Framework(name="Unknown", slug="unknown", is_active=True),
                Framework(name="Astro", slug="astro", is_active=True),
                Category(name="General", slug="general", is_active=True),
                Category(name="Portfolio", slug="portfolio", is_active=True),
            ]
        )
        await session.commit()
    return engine, factory


@pytest.mark.asyncio
async def test_provider_auto_create_and_sync_history(tmp_path) -> None:
    engine, factory = await _database(tmp_path, "provider.db")
    registry = AdapterRegistry([OwnerAdapter()])
    imported = await TemplateImportService(factory, registry).import_repository(
        repository_url="https://github.com/acme/owner-template",
        requested_by="admin-1",
    )
    assert imported.provider.slug == "github-acme"
    assert imported.provider.name == "Acme Studio"
    assert imported.provider.website_url == "https://github.com/acme"

    async with factory() as session:
        histories = list(
            (await session.scalars(select(SyncHistory).order_by(SyncHistory.created_at))).all()
        )
        assert len(histories) == 1
        assert histories[0].status == ImportStatus.SUCCEEDED
        assert histories[0].trigger == "initial_import"
        assert histories[0].requested_by == "admin-1"

    await TemplateSyncService(factory, registry).sync_one(imported.id, requested_by="admin-2")
    async with factory() as session:
        histories = list(
            (await session.scalars(select(SyncHistory).order_by(SyncHistory.created_at))).all()
        )
        assert len(histories) == 2
        assert histories[-1].trigger == "manual"
        assert histories[-1].requested_by == "admin-2"
        assert histories[-1].changes is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_manual_asset_add_update_delete(tmp_path) -> None:
    engine, factory = await _database(tmp_path, "assets.db")
    async with factory() as session:
        framework = await session.scalar(select(Framework).where(Framework.slug == "astro"))
        template = Template(
            name="Asset Template",
            slug="asset-template",
            repository_url="https://github.com/acme/assets",
            repository_adapter="github",
            default_branch="main",
            screenshots=[],
            topics=[],
            manifest={},
            analysis={},
            quality_breakdown={},
            framework=framework,
        )
        session.add(template)
        await session.commit()
        asset = await TemplateAssetService.add_manual(
            session,
            template_id=template.id,
            url="https://cdn.example.com/a.png",
            kind="screenshot",
            sort_order=2,
        )
        assert asset.source == "manual"
        updated = await TemplateAssetService.update_manual(
            session,
            asset_id=asset.id,
            url="https://cdn.example.com/b.webp",
            kind="thumbnail",
            sort_order=0,
        )
        assert updated.kind == "thumbnail"
        refreshed = await session.get(Template, template.id)
        assert refreshed.thumbnail_url == "https://cdn.example.com/b.webp"
        await TemplateAssetService.delete_manual(session, asset.id)
        assert await session.get(TemplateAsset, asset.id) is None
    await engine.dispose()


class FakeScreenshotService:
    enabled = True

    async def generate_with_metadata(self, preview_url: str) -> tuple[str, dict[str, Any]]:
        assert preview_url == "https://preview.example.com"
        return "https://cdn.example.com/generated.webp", {"width": 1440, "height": 900}


@pytest.mark.asyncio
async def test_screenshot_job_records_result(tmp_path) -> None:
    engine, factory = await _database(tmp_path, "screenshot.db")
    async with factory() as session:
        framework = await session.scalar(select(Framework).where(Framework.slug == "astro"))
        template = Template(
            name="Screenshot Template",
            slug="screenshot-template",
            repository_url="https://github.com/acme/screenshot",
            repository_adapter="github",
            default_branch="main",
            preview_url="https://preview.example.com",
            screenshots=[],
            topics=[],
            manifest={},
            analysis={},
            quality_breakdown={},
            framework=framework,
        )
        session.add(template)
        await session.commit()
        template_id = template.id

    job = await ScreenshotJobService(factory, FakeScreenshotService()).create_and_run(
        template_id, "admin"
    )
    assert job.status == ScreenshotJobStatus.SUCCEEDED
    assert job.screenshot_url == "https://cdn.example.com/generated.webp"
    async with factory() as session:
        template = await session.get(Template, template_id)
        assert template.thumbnail_url == "https://cdn.example.com/generated.webp"
        jobs = list((await session.scalars(select(ScreenshotJob))).all())
        assert len(jobs) == 1
        assets = list((await session.scalars(select(TemplateAsset))).all())
        assert any(asset.source == "screenshot-service" for asset in assets)
    await engine.dispose()


def test_readme_media_and_public_url_security() -> None:
    text = '![Preview](docs/preview.png)\n<img src="https://cdn.example.com/demo.webp">'
    assert extract_readme_image_references(text) == [
        "docs/preview.png",
        "https://cdn.example.com/demo.webp",
    ]
    assert is_probable_template_image("src/assets/home-screenshot.png")
    assert validate_public_https_url("https://preview.example.com") == "https://preview.example.com"
    with pytest.raises(ValidationError):
        validate_public_https_url("https://127.0.0.1/secret")
    with pytest.raises(ValidationError):
        validate_public_https_url("https://service.internal/secret")


@pytest.mark.asyncio
async def test_public_filters_assets_freshness_and_facets(tmp_path) -> None:
    engine, factory = await _database(tmp_path, "api-service.db")
    async with factory() as session:
        framework = await session.scalar(select(Framework).where(Framework.slug == "astro"))
        category = await session.scalar(select(Category).where(Category.slug == "portfolio"))
        provider = Provider(
            name="Acme Studio",
            slug="github-acme",
            is_active=True,
        )
        template = Template(
            name="Published Astro",
            slug="published-astro",
            repository_url="https://github.com/acme/published",
            repository_adapter="github",
            default_branch="main",
            screenshots=["https://cdn.example.com/preview.png"],
            topics=["astro", "portfolio"],
            primary_language="TypeScript",
            difficulty="beginner",
            use_case="portfolio",
            quality_score=90,
            status=TemplateStatus.PUBLISHED,
            published_at=datetime.now(UTC),
            last_synced_at=datetime.now(UTC),
            source_updated_at=datetime.now(UTC),
            manifest={
                "schema_version": "2.0",
                "name": "Published Astro",
                "framework": "astro",
                "repository": "https://github.com/acme/published",
                "branch": "main",
                "deploy": {"type": "static"},
                "environment": [],
            },
            analysis={},
            quality_breakdown={},
            framework=framework,
            category=category,
            provider=provider,
        )
        session.add(template)
        await session.flush()
        session.add(
            TemplateAsset(
                template=template,
                kind="screenshot",
                url="https://cdn.example.com/preview.png",
                source="github",
            )
        )
        session.add(
            SyncHistory(
                template=template,
                adapter="github",
                trigger="initial_import",
                status=ImportStatus.SUCCEEDED,
                source_revision="abc",
                completed_at=datetime.now(UTC),
            )
        )
        await session.commit()

        records, total, pages = await TemplateService.list_public(
            session,
            page=1,
            page_size=20,
            search=None,
            category="portfolio",
            provider="github-acme",
            framework="astro",
            featured=None,
            language="typescript",
            difficulty="beginner",
            use_case="portfolio",
            min_quality=80,
            sort="quality",
            order="desc",
        )
        assert total == 1 and pages == 1 and records[0].slug == "published-astro"
        assets = await TemplateService.list_public_assets(session, "published-astro")
        assert len(assets) == 1
        freshness = await TemplateService.public_freshness(session, "published-astro")
        assert freshness["source_revision"] == "abc"
        facets = await TemplateService.public_facets(session)
        assert any(item["slug"] == "github-acme" for item in facets["providers"])
    await engine.dispose()


def test_entity_headers_accept_naive_datetime() -> None:
    from datetime import datetime

    from starlette.requests import Request
    from starlette.responses import Response

    from app.api.v1.catalog import _entity_headers

    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    response = Response()
    assert not _entity_headers(request, response, "template-1", datetime(2026, 1, 1))
    assert response.headers["ETag"]
    assert response.headers["Last-Modified"].endswith("GMT")


@pytest.mark.asyncio
async def test_manual_preview_asset_updates_template_preview(tmp_path) -> None:
    engine, factory = await _database(tmp_path, "preview-assets.db")
    async with factory() as session:
        framework = await session.scalar(select(Framework).where(Framework.slug == "astro"))
        template = Template(
            name="Preview Asset Template",
            slug="preview-asset-template",
            repository_url="https://github.com/acme/preview-assets",
            repository_adapter="github",
            default_branch="main",
            preview_url="https://old-preview.example.com",
            screenshots=[],
            topics=[],
            manifest={},
            analysis={},
            quality_breakdown={},
            framework=framework,
        )
        session.add(template)
        await session.commit()
        asset = await TemplateAssetService.add_manual(
            session,
            template_id=template.id,
            url="https://preview.example.com",
            kind="preview",
        )
        refreshed = await session.get(Template, template.id)
        assert refreshed.preview_url == "https://preview.example.com"

        await TemplateAssetService.update_manual(
            session,
            asset_id=asset.id,
            url="https://cdn.example.com/new-screen.webp",
            kind="screenshot",
            sort_order=0,
        )
        refreshed = await session.get(Template, template.id)
        assert refreshed.preview_url is None
        assert refreshed.thumbnail_url == "https://cdn.example.com/new-screen.webp"

        await TemplateAssetService.delete_manual(session, asset.id)
        refreshed = await session.get(Template, template.id)
        assert refreshed.screenshots == []
        assert refreshed.thumbnail_url is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_screenshot_job_retry_creates_a_tracked_attempt(tmp_path) -> None:
    engine, factory = await _database(tmp_path, "screenshot-retry.db")
    async with factory() as session:
        framework = await session.scalar(select(Framework).where(Framework.slug == "astro"))
        template = Template(
            name="Retry Screenshot Template",
            slug="retry-screenshot-template",
            repository_url="https://github.com/acme/retry-screenshot",
            repository_adapter="github",
            default_branch="main",
            preview_url="https://preview.example.com",
            screenshots=[],
            topics=[],
            manifest={},
            analysis={},
            quality_breakdown={},
            framework=framework,
        )
        session.add(template)
        await session.commit()
        template_id = template.id

    service = ScreenshotJobService(factory, FakeScreenshotService())
    first = await service.create_and_run(template_id, "admin-1")
    second = await service.retry(first.id, "admin-2")
    assert second.id != first.id
    assert second.status == ScreenshotJobStatus.SUCCEEDED
    async with factory() as session:
        jobs = list((await session.scalars(select(ScreenshotJob))).all())
        assert len(jobs) == 2
        assert {job.requested_by for job in jobs} == {"admin-1", "admin-2"}
    await engine.dispose()


class _FakeBitbucketResponse:
    status_code = 200

    def __init__(self, values: list[dict[str, str]]) -> None:
        self._values = values

    def json(self) -> dict[str, object]:
        return {"values": self._values}


class _FakeBitbucketHTTP:
    async def get(self, url: str, params: object = None) -> _FakeBitbucketResponse:
        del params
        if url.endswith("/main/public/images"):
            return _FakeBitbucketResponse(
                [{"type": "commit_file", "path": "public/images/hero-preview.png"}]
            )
        if url.endswith("/main/public"):
            return _FakeBitbucketResponse([{"type": "commit_directory", "path": "public/images"}])
        return _FakeBitbucketResponse(
            [
                {"type": "commit_directory", "path": "public"},
                {"type": "commit_file", "path": "README.md"},
            ]
        )


@pytest.mark.asyncio
async def test_bitbucket_recursive_scan_reaches_nested_media() -> None:
    from app.integrations.bitbucket.client import BitbucketClient

    client = BitbucketClient(None, None, 5)
    await client.close()
    client._client = _FakeBitbucketHTTP()  # type: ignore[assignment]
    paths = await client._recursive_paths("acme", "starter", "main")
    assert "public/images/hero-preview.png" in paths


def test_readme_media_filter_rejects_logos_and_badges() -> None:
    from app.analyzer.media import is_readme_media_candidate

    assert is_readme_media_candidate("docs/home-preview.png")
    assert not is_readme_media_candidate("assets/company-logo.png")
    assert not is_readme_media_candidate("https://img.shields.io/status-badge.png")
