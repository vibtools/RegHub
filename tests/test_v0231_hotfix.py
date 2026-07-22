from __future__ import annotations

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqladmin import Admin
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.middleware.sessions import SessionMiddleware

from app.admin.views import SettingsView
from app.core.config import Settings
from app.core.enums import OperationStatus
from app.database.base import Base
from app.operations.service import OperationRunner, OperationService
from app.runtime.api_access import ApiAccessService
from app.runtime.settings import RuntimeSettingsService
from tests.support import super_admin_identity


def test_settings_actions_preserve_active_tab_and_api_check_uses_root_app(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'v0231-settings.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///unused.db",
        session_secret=SecretStr("v0231-hotfix-secret-with-more-than-thirty-two-characters"),
    )
    runtime = RuntimeSettingsService(session_factory, settings)
    api_access = ApiAccessService(
        session_factory, "v0231-api-access-secret-with-more-than-thirty-two-characters"
    )

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await runtime.initialize()
        await api_access.initialize()

    asyncio.run(prepare())

    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="v0231-test-session-secret")

    @app.middleware("http")
    async def add_identity(request, call_next):
        request.state.admin_identity = super_admin_identity()
        request.state.request_id = "v0231-request"
        return await call_next(request)

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok", "service": "reghub"}

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

    with TestClient(app) as client:
        page = client.get("/admin/settings#api-manage-pane")
        assert page.status_code == 200
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        assert csrf is not None

        saved = client.post(
            "/admin/settings",
            data={
                "csrf_token": csrf.group(1),
                "action": "save_api_mode",
                "api_mode": "development",
                "return_tab": "api-manage-pane",
            },
        )
        assert saved.status_code == 200
        assert 'const serverRequested = "#api-manage-pane"' in saved.text
        assert "API access mode updated immediately" in saved.text

        checked = client.post(
            "/admin/settings/api-check",
            data={"csrf_token": csrf.group(1), "endpoint_id": "health"},
        )
        assert checked.status_code == 200
        payload = checked.json()
        assert payload["results"][0]["endpoint_id"] == "health"
        assert payload["results"][0]["status"] == 200
        assert payload["results"][0]["ok"] is True
        assert "admin:statics" not in str(payload)

    asyncio.run(engine.dispose())


def test_api_endpoint_registry_and_compact_terminal_markup_are_present() -> None:
    root = Path(__file__).parents[1]
    settings = (root / "templates" / "settings.html").read_text()
    detail = (root / "templates" / "operation_detail.html").read_text()
    layout = (root / "templates" / "reghub_layout.html").read_text()

    assert "API endpoint registry" in settings
    assert "api-check-one" in settings
    assert "api-use-one" in settings
    assert "endpoint_id" in settings
    assert "PowerShell:" in settings
    assert "Authorization: Bearer" in settings
    assert "return_tab" in settings

    assert "reghub-log-content" in detail
    assert "Object.keys(data.data).length" in detail
    assert ".reghub-log-content" in layout
    assert ".reghub-log-data:empty" in layout
    assert "grid-column: 3" not in layout


def test_operation_failure_records_redacted_payload_and_traceback(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'v0231-logs.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def run():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        service = OperationService(session_factory)
        operation = await service.create(
            operation_type="unsupported_hotfix_test",
            title="Detailed log test",
            requested_by="admin-user",
            input_payload={"api_token": "very-secret-value", "safe": "visible"},
        )
        runner = OperationRunner(service)
        runner.bind(SimpleNamespace())
        await runner._execute(operation.id)
        return await service.get(operation.id, with_logs=True)

    operation = asyncio.run(run())
    assert operation.status == OperationStatus.FAILED
    payload_log = next(item for item in operation.logs if item.message == "Input payload accepted")
    assert payload_log.data["payload"]["api_token"] == "[REDACTED]"
    assert payload_log.data["payload"]["safe"] == "visible"
    failure_log = next(item for item in operation.logs if item.message.startswith("FAILED stage="))
    assert failure_log.data["exception_type"] == "ValidationError"
    assert "Traceback" in failure_log.data["traceback"]
    assert "very-secret-value" not in str(operation.logs)

    asyncio.run(engine.dispose())
