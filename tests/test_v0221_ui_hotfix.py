import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqladmin import Admin
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.middleware.sessions import SessionMiddleware

from app.admin.views import OperationsConsoleView, SettingsView
from app.core.config import Settings
from app.database.base import Base
from app.operations.service import OperationService
from app.runtime.settings import RuntimeSettingsService
from tests.support import super_admin_identity

CUSTOM_TEMPLATES = [
    "asset_gallery.html",
    "github_import.html",
    "local_import.html",
    "operation_detail.html",
    "operations_list.html",
    "registry_import.html",
    "settings.html",
    "sqladmin/index.html",
]


def test_all_custom_admin_pages_use_full_width_hotfix_layout() -> None:
    template_root = Path(__file__).parents[1] / "templates"
    for relative_path in CUSTOM_TEMPLATES:
        first_line = (template_root / relative_path).read_text().splitlines()[0]
        assert first_line == '{% extends "reghub_layout.html" %}'

    layout = (template_root / "reghub_layout.html").read_text()
    assert 'class="col-12 reghub-page-shell"' in layout
    assert ".reghub-page-shell" in layout
    assert "overflow-wrap: anywhere" in layout


def test_settings_is_compact_tabbed_and_operation_page_has_polling_fallback(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ui-hotfix.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///unused.db",
        session_secret=SecretStr("ui-hotfix-test-secret-with-more-than-32-characters"),
    )
    runtime = RuntimeSettingsService(session_factory, settings)
    operation_service = OperationService(session_factory)

    async def prepare():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await runtime.initialize()
        operation = await operation_service.create(
            operation_type="sync_templates",
            title="UI hotfix operation",
            requested_by="admin-user",
            return_url="/admin/template/list",
        )
        await operation_service.append_log(operation.id, "Visible initial log", progress=40)
        return operation

    operation = asyncio.run(prepare())
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="ui-hotfix-session-secret")

    @app.middleware("http")
    async def add_identity(request, call_next):
        request.state.admin_identity = super_admin_identity()
        return await call_next(request)

    async def reload_runtime() -> None:
        return None

    app.state.container = SimpleNamespace(
        runtime_settings=runtime,
        operation_service=operation_service,
        feature_enabled=runtime.feature_enabled,
        reload_runtime=reload_runtime,
    )
    admin = Admin(app=app, engine=engine, base_url="/admin", templates_dir="templates")
    admin.add_view(OperationsConsoleView)
    admin.add_view(SettingsView)

    with TestClient(app) as client:
        settings_response = client.get("/admin/settings")
        assert settings_response.status_code == 200
        assert 'class="col-12 reghub-page-shell"' in settings_response.text
        assert 'id="features-pane"' in settings_response.text
        assert 'id="integrations-pane"' in settings_response.text
        assert 'id="custom-api-pane"' in settings_response.text
        assert 'id="integrationAccordion"' in settings_response.text

        detail = client.get(f"/admin/operations/{operation.id}")
        assert detail.status_code == 200
        assert 'class="col-12 reghub-page-shell"' in detail.text
        assert "Visible initial log" in detail.text
        assert "Polling fallback" in detail.text
        assert "/admin/operations/${operationId}/logs.json" in detail.text

        logs = client.get(f"/admin/operations/{operation.id}/logs.json", params={"after": 0})
        assert logs.status_code == 200
        payload = logs.json()
        assert payload["status"] == "queued"
        assert payload["progress"] == 40
        assert [item["message"] for item in payload["logs"]] == [
            "Operation queued",
            "Visible initial log",
        ]

        later_logs = client.get(f"/admin/operations/{operation.id}/logs.json", params={"after": 1})
        assert later_logs.status_code == 200
        assert [item["message"] for item in later_logs.json()["logs"]] == ["Visible initial log"]

    asyncio.run(engine.dispose())
