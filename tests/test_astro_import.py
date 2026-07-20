from typing import Any

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.models.framework import Framework
from app.registry.adapters.base import ImportedRepository, RegistryAdapter
from app.registry.adapters.registry import AdapterRegistry
from app.registry.template import TemplateImportService


class FakeGitHubAdapter(RegistryAdapter):
    name = "github"

    async def import_repository(self, repository_url: str) -> ImportedRepository:
        package_json: dict[str, Any] = {
            "dependencies": {
                "astro": "^5.0.0",
                "react": "^19.0.0",
            }
        }
        return ImportedRepository(
            adapter="github",
            external_id="astro-1",
            name="astro-starter",
            description="Astro starter template",
            repository_url=repository_url,
            default_branch="main",
            homepage_url=None,
            license_spdx="MIT",
            topics=[],
            primary_language="TypeScript",
            stars_count=1,
            forks_count=0,
            root_files=frozenset({"package.json", "src"}),
            package_json=package_json,
            metadata={"package_json_detected": True},
        )


@pytest.mark.asyncio
async def test_astro_repository_import_creates_astro_manifest(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'astro-import.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        session.add_all(
            [
                Framework(name="Unknown", slug="unknown", is_active=True),
                Framework(name="Astro", slug="astro", is_active=True),
            ]
        )
        await session.commit()

    service = TemplateImportService(
        session_factory,
        AdapterRegistry([FakeGitHubAdapter()]),
    )
    template = await service.import_repository(
        repository_url="https://github.com/ygit/astro-starter",
        requested_by="admin-user",
    )

    assert template.framework.slug == "astro"
    assert template.manifest["framework"] == "astro"
    assert template.manifest["deploy"]["type"] == "static"
    assert template.status.value == "draft"

    await engine.dispose()
