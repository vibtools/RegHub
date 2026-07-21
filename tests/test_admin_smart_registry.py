import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqladmin import Admin
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.admin.views import (
    SyncHistoryAdmin,
    TemplateAdmin,
    TemplateAssetAdmin,
    TemplateVersionAdmin,
)
from app.core.enums import ImportStatus, TemplateStatus
from app.database.base import Base
from app.models.framework import Framework
from app.models.sync_history import SyncHistory
from app.models.template import Template
from app.models.template_asset import TemplateAsset
from app.models.template_version import TemplateVersion


def test_smart_registry_admin_lists_render(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'admin-smart.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            framework = Framework(name="Astro", slug="astro", is_active=True)
            template = Template(
                name="Smart Astro",
                slug="smart-astro",
                repository_url="https://github.com/ygit/smart-astro",
                default_branch="main",
                repository_adapter="github",
                topics=["astro"],
                screenshots=[],
                manifest={
                    "schema_version": "2.0",
                    "name": "Smart Astro",
                    "framework": "astro",
                    "repository": "https://github.com/ygit/smart-astro",
                    "branch": "main",
                    "deploy": {"type": "static"},
                    "environment": [],
                },
                analysis={},
                quality_breakdown={},
                status=TemplateStatus.DRAFT,
                framework=framework,
            )
            session.add(template)
            await session.flush()
            session.add_all(
                [
                    TemplateVersion(
                        template=template,
                        source_revision="abc",
                        metadata_snapshot={},
                        manifest_snapshot=template.manifest,
                        analysis_snapshot={},
                    ),
                    SyncHistory(
                        template=template,
                        adapter="github",
                        status=ImportStatus.SUCCEEDED,
                    ),
                    TemplateAsset(
                        template=template,
                        kind="screenshot",
                        url="https://example.com/image.png",
                        source="github",
                    ),
                ]
            )
            await session.commit()

    asyncio.run(prepare())
    app = FastAPI()
    admin = Admin(app=app, engine=engine, base_url="/admin")
    for view in (TemplateAdmin, TemplateVersionAdmin, SyncHistoryAdmin, TemplateAssetAdmin):
        admin.add_view(view)

    with TestClient(app) as client:
        for path in (
            "/admin/template/list",
            "/admin/template-version/list",
            "/admin/sync-history/list",
            "/admin/template-asset/list",
        ):
            response = client.get(path)
            assert response.status_code == 200, path

    asyncio.run(engine.dispose())
