from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.enums import ProviderType, TemplateStatus
from app.database.base import Base
from app.models.category import Category
from app.models.framework import Framework
from app.models.provider import Provider
from app.models.template_version import TemplateVersion
from app.registry.adapters.base import ImportedRepository, RegistryAdapter
from app.registry.adapters.registry import AdapterRegistry
from app.registry.template import TemplateImportService, TemplateSyncService


class MutableAdapter(RegistryAdapter):
    name = "github"

    def __init__(self) -> None:
        self.version = "5.0.0"
        self.stars = 10

    async def import_repository(self, repository_url: str) -> ImportedRepository:
        package_json: dict[str, Any] = {
            "dependencies": {"astro": self.version},
            "devDependencies": {"typescript": "5.0.0"},
            "scripts": {"build": "astro build", "preview": "astro preview"},
        }
        return ImportedRepository(
            adapter="github",
            external_id="astro-smart-1",
            name="astro-smart",
            description="Astro portfolio template",
            repository_url=repository_url,
            default_branch="main",
            homepage_url="https://demo.example.com",
            license_spdx="MIT",
            topics=["portfolio"],
            primary_language="TypeScript",
            stars_count=self.stars,
            forks_count=2,
            root_files=frozenset(
                {"package.json", "pnpm-lock.yaml", "astro.config.mjs", ".env.example"}
            ),
            package_json=package_json,
            metadata={"revision": self.version},
            source_revision=self.version,
            source_updated_at=datetime.now(UTC),
            readme_text="# Astro Smart\n" + "Documentation. " * 50,
            env_example_text="PUBLIC_API_URL=https://example.com\n",
            screenshot_urls=["https://example.com/astro.png"],
        )


@pytest.mark.asyncio
async def test_import_creates_manifest_analysis_and_version(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'smart.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        session.add_all(
            [
                Framework(name="Unknown", slug="unknown", is_active=True),
                Framework(name="Astro", slug="astro", is_active=True),
                Category(name="General", slug="general", is_active=True),
                Category(name="Portfolio", slug="portfolio", is_active=True),
                Provider(
                    name="Community",
                    slug="community",
                    provider_type=ProviderType.COMMUNITY,
                    is_active=True,
                ),
            ]
        )
        await session.commit()

    adapter = MutableAdapter()
    registry = AdapterRegistry([adapter])
    service = TemplateImportService(session_factory, registry)
    template = await service.import_repository(
        repository_url="https://github.com/community/astro-smart",
        requested_by="admin",
    )
    assert template.status == TemplateStatus.DRAFT
    assert template.framework.slug == "astro"
    assert template.framework_version == "5.0.0"
    assert template.package_manager == "pnpm"
    assert template.category.slug == "portfolio"
    assert template.provider.slug == "community"
    assert template.quality_score > 0
    assert template.manifest["schema_version"] == "2.0"
    assert template.manifest["build"]["command"] == "pnpm build"
    async with session_factory() as session:
        versions = list((await session.scalars(select(TemplateVersion))).all())
        assert len(versions) == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_sync_preserves_curated_identity_and_status(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sync.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        session.add_all(
            [
                Framework(name="Unknown", slug="unknown", is_active=True),
                Framework(name="Astro", slug="astro", is_active=True),
                Category(name="General", slug="general", is_active=True),
                Category(name="Portfolio", slug="portfolio", is_active=True),
                Provider(
                    name="Community",
                    slug="community",
                    provider_type=ProviderType.COMMUNITY,
                    is_active=True,
                ),
            ]
        )
        await session.commit()

    adapter = MutableAdapter()
    registry = AdapterRegistry([adapter])
    imported = await TemplateImportService(session_factory, registry).import_repository(
        repository_url="https://github.com/community/astro-smart",
        requested_by="admin",
    )
    async with session_factory() as session:
        record = await session.get(type(imported), imported.id)
        record.name = "Curated Display Name"
        record.status = TemplateStatus.PUBLISHED
        await session.commit()

    adapter.version = "5.3.0"
    adapter.stars = 99
    synced = await TemplateSyncService(session_factory, registry).sync_one(imported.id)
    assert synced.name == "Curated Display Name"
    assert synced.status == TemplateStatus.PUBLISHED
    assert synced.framework_version == "5.3.0"
    assert synced.stars_count == 99

    async with session_factory() as session:
        versions = list((await session.scalars(select(TemplateVersion))).all())
        assert len(versions) == 2
    await engine.dispose()
