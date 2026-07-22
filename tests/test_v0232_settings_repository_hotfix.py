from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqladmin import Admin
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.middleware.sessions import SessionMiddleware

from app.admin.views import SettingsView
from app.api.v1.router import router as api_v1_router
from app.core.config import Settings
from app.core.enums import ImportStatus, TemplateStatus
from app.database.base import Base
from app.database.session import get_db_session
from app.models.sync_history import SyncHistory
from app.models.template import Template
from app.runtime.api_access import ApiAccessService
from app.runtime.settings import RuntimeSettingsService
from tests.support import super_admin_identity


def _settings_app(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'v0232-settings.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///unused.db",
        session_secret=SecretStr("v0232-settings-secret-with-more-than-thirty-two-characters"),
    )
    runtime = RuntimeSettingsService(session_factory, settings)
    api_access = ApiAccessService(
        session_factory, "v0232-api-access-secret-with-more-than-thirty-two-characters"
    )

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await runtime.initialize()
        await api_access.initialize()

    asyncio.run(prepare())
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="v0232-session-secret")

    @app.middleware("http")
    async def add_identity(request, call_next):
        request.state.admin_identity = super_admin_identity()
        request.state.request_id = "v0232-request"
        return await call_next(request)

    async def reload_runtime() -> None:
        return None

    app.state.container = SimpleNamespace(
        runtime_settings=runtime,
        api_access=api_access,
        session_factory=session_factory,
        feature_enabled=runtime.feature_enabled,
        reload_runtime=reload_runtime,
    )
    admin = Admin(app=app, engine=engine, base_url="/admin", templates_dir="templates")
    admin.add_view(SettingsView)
    return app, engine


def test_settings_actions_use_ajax_and_server_render_the_requested_pane(tmp_path: Path) -> None:
    app, engine = _settings_app(tmp_path)
    with TestClient(app) as client:
        page = client.get("/admin/settings?tab=integrations-pane")
        assert page.status_code == 200
        assert re.search(r'class="nav-link active" id="integrations-tab"', page.text)
        assert re.search(r'class="tab-pane fade show active" id="integrations-pane"', page.text)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        assert csrf is not None

        saved = client.post(
            "/admin/settings?tab=integrations-pane",
            data={
                "csrf_token": csrf.group(1),
                "action": "reload_runtime",
                "return_tab": "integrations-pane",
            },
        )
        assert saved.status_code == 200
        assert re.search(r'class="nav-link active" id="integrations-tab"', saved.text)
        assert re.search(r'class="tab-pane fade show active" id="integrations-pane"', saved.text)

    asyncio.run(engine.dispose())


def test_settings_template_intercepts_every_settings_form_and_removes_dev_banners() -> None:
    root = Path(__file__).parents[1]
    settings = (root / "templates" / "settings.html").read_text(encoding="utf-8")
    github = (root / "templates" / "github_import.html").read_text(encoding="utf-8")
    registry = (root / "templates" / "registry_import.html").read_text(encoding="utf-8")
    local = (root / "templates" / "local_import.html").read_text(encoding="utf-8")

    assert "data-settings-form" in settings
    assert "submitSettingsForm" in settings
    assert "current.replaceWith(nextPane)" in settings
    assert "currentShell.replaceWith(nextShell)" not in settings
    assert "fetch(`${actionUrl.pathname}${actionUrl.search}`" in settings
    assert "return_tab" in settings
    assert "activatePane" in settings
    assert "After submission, RegHub opens" not in github
    assert "GitHub API is authenticated" not in github
    assert "After submission, RegHub opens" not in registry
    assert "background operation with live progress" not in local


def test_original_repository_endpoint_and_settings_registry(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'v0232-repository.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            template = Template(
                name="Published Source",
                slug="published-source",
                repository_url="https://github.com/example/published-source",
                repository_adapter="github",
                external_repository_id="repo-123",
                default_branch="main",
                screenshots=[],
                topics=[],
                manifest={
                    "schema_version": "2.0",
                    "name": "Published Source",
                    "framework": "static-html",
                    "repository": "https://github.com/example/published-source",
                    "branch": "main",
                    "deploy": {"type": "static"},
                    "environment": [],
                },
                analysis={},
                quality_breakdown={},
                status=TemplateStatus.PUBLISHED,
                published_at=datetime.now(UTC),
            )
            session.add(template)
            await session.flush()
            session.add(
                SyncHistory(
                    template=template,
                    adapter="github",
                    trigger="initial_import",
                    status=ImportStatus.SUCCEEDED,
                    source_revision="abc123",
                    completed_at=datetime.now(UTC),
                )
            )
            await session.commit()

    asyncio.run(prepare())

    class ApiAccess:
        mode = "development"
        live_mode = False

        async def authorize(self, request, scope: str) -> None:
            return None

    app = FastAPI()
    app.include_router(api_v1_router)

    @app.middleware("http")
    async def add_context(request, call_next):
        request.state.request_id = "v0232-api-request"
        return await call_next(request)

    app.state.container = SimpleNamespace(
        require_feature=lambda *_args, **_kwargs: None,
        api_access=ApiAccess(),
    )

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session

    with TestClient(app) as client:
        response = client.get("/api/v1/templates/published-source/repository")
        assert response.status_code == 200
        payload = response.json()
        assert payload["data"]["repository_url"] == ("https://github.com/example/published-source")
        assert payload["data"]["repository_adapter"] == "github"
        assert payload["data"]["source_revision"] == "abc123"
        assert payload["meta"]["request_id"] == "v0232-api-request"

    settings_markup = (Path(__file__).parents[1] / "templates" / "settings.html").read_text(
        encoding="utf-8"
    )
    api_catalog = (Path(__file__).parents[1] / "app" / "runtime" / "api_catalog.py").read_text(
        encoding="utf-8"
    )
    assert "Original repository" in api_catalog
    assert "template_repository" in api_catalog
    assert "apiEndpointTable" in settings_markup
    asyncio.run(engine.dispose())
