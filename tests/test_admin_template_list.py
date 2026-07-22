import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqladmin import Admin
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.admin.views import TemplateAdmin
from app.core.enums import ProviderType, TemplateStatus
from app.database.base import Base
from app.models.category import Category
from app.models.framework import Framework
from app.models.provider import Provider
from app.models.template import Template
from tests.support import super_admin_identity


def test_template_admin_list_and_filters_render(tmp_path: Path) -> None:
    database_path = tmp_path / "admin-list.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare_database() -> str:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            category = Category(name="General", slug="general", is_active=True)
            provider = Provider(
                name="YGIT Official",
                slug="official",
                provider_type=ProviderType.OFFICIAL,
                is_active=True,
            )
            framework = Framework(name="Astro", slug="astro", is_active=True)
            template = Template(
                name="Astro Starter",
                slug="astro-starter",
                repository_url="https://github.com/ygit/astro-starter",
                default_branch="main",
                topics=["astro"],
                manifest={
                    "schema_version": "1.0",
                    "framework": "astro",
                    "repository": "https://github.com/ygit/astro-starter",
                    "branch": "main",
                    "deploy": {"type": "static"},
                },
                status=TemplateStatus.DRAFT,
                category=category,
                provider=provider,
                framework=framework,
            )
            session.add(template)
            await session.commit()
            return str(framework.id)

    framework_id = asyncio.run(prepare_database())

    app = FastAPI()

    @app.middleware("http")
    async def add_identity(request, call_next):
        request.state.admin_identity = super_admin_identity()
        return await call_next(request)

    admin = Admin(app=app, engine=engine, base_url="/admin")
    admin.add_view(TemplateAdmin)

    with TestClient(app) as client:
        response = client.get("/admin/template/list")
        assert response.status_code == 200
        assert "Astro Starter" in response.text

        response = client.get("/admin/template/list?flt0_0=DRAFT")
        assert response.status_code == 200
        assert "Astro Starter" in response.text

        response = client.get("/admin/template/list?flt1_0=false")
        assert response.status_code == 200
        assert "Astro Starter" in response.text

        response = client.get(f"/admin/template/list?flt2_0={framework_id}")
        assert response.status_code == 200
        assert "Astro Starter" in response.text

    asyncio.run(engine.dispose())
