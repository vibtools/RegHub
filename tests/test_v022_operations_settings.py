import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqladmin import Admin
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.middleware.sessions import SessionMiddleware

from app.admin.views import OperationsConsoleView, SettingsView, TemplateAdmin
from app.core.config import Settings
from app.core.enums import OperationStatus, TemplateStatus
from app.database.base import Base
from app.models.admin_operation import AdminOperation
from app.models.category import Category
from app.models.framework import Framework
from app.models.integration_config import IntegrationConfig
from app.models.provider import Provider
from app.models.template import Template
from app.operations.service import OperationService
from app.registry.template import TemplateService
from app.runtime.settings import RuntimeSettingsService


async def _database(tmp_path: Path, name: str):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / name}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, session_factory


@pytest.mark.asyncio
async def test_runtime_settings_are_immediate_encrypted_and_removable(tmp_path: Path) -> None:
    engine, session_factory = await _database(tmp_path, "runtime-settings.db")
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///unused.db",
        session_secret=SecretStr("runtime-settings-test-secret-with-more-than-32-characters"),
        github_token=SecretStr("env-github-token"),
        ai_metadata_enabled=False,
    )
    runtime = RuntimeSettingsService(session_factory, settings)
    await runtime.initialize()

    assert runtime.feature_enabled("github_import") is True
    assert runtime.feature_enabled("ai_metadata") is False
    assert runtime.integration("github").secret == "env-github-token"

    await runtime.update_feature(
        "github_import",
        enabled=False,
        admin_task_allowed=False,
        updated_by="admin-user",
    )
    assert runtime.feature_enabled("github_import") is False
    assert runtime.feature_enabled("github_import", task=True) is False

    await runtime.upsert_integration(
        slug="github",
        name="GitHub",
        integration_type="source_provider",
        enabled=True,
        base_url=None,
        username=None,
        secret="runtime-github-token",
        clear_secret=False,
        use_environment_fallback=False,
        config={"timeout": 19, "allow_private": False},
        updated_by="admin-user",
    )
    assert runtime.integration("github").secret == "runtime-github-token"
    assert runtime.integration("github").source == "runtime"

    await runtime.upsert_integration(
        slug="ai",
        name="AI Metadata",
        integration_type="ai",
        enabled=True,
        base_url="https://api.example.com/v1",
        username=None,
        secret="ai-runtime-token",
        clear_secret=False,
        use_environment_fallback=False,
        config={"model": "example-model"},
        updated_by="admin-user",
    )
    assert runtime.integration("ai").enabled is True
    assert runtime.integration("ai").secret == "ai-runtime-token"

    async with session_factory() as session:
        row = await session.scalar(
            select(IntegrationConfig).where(IntegrationConfig.slug == "github")
        )
        assert row is not None
        assert row.secret_encrypted is not None
        assert "runtime-github-token" not in row.secret_encrypted
        assert row.updated_by == "admin-user"

    custom = await runtime.upsert_integration(
        slug="example-api",
        name="Example API",
        integration_type="custom",
        enabled=True,
        base_url="https://api.example.com",
        username="service-user",
        secret="custom-secret",
        clear_secret=False,
        use_environment_fallback=False,
        config={"scope": "registry-read"},
        updated_by="admin-user",
    )
    assert custom.is_system is False
    assert runtime.integration("example-api").enabled is True
    assert runtime.integration("example-api").secret == "custom-secret"

    await runtime.remove_integration("example-api", updated_by="admin-user")
    with pytest.raises(Exception, match="not configured"):
        runtime.integration("example-api")

    await runtime.remove_integration("github", updated_by="admin-user")
    github = runtime.integration("github")
    assert github.enabled is False
    assert github.secret is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_operation_service_lifecycle_logs_retry_and_recovery(tmp_path: Path) -> None:
    engine, session_factory = await _database(tmp_path, "operations.db")
    service = OperationService(session_factory)

    operation = await service.create(
        operation_type="sync_templates",
        title="Synchronize templates",
        requested_by="admin-user",
        input_payload={"template_ids": []},
        return_url="/admin/template/list",
    )
    assert operation.status == OperationStatus.QUEUED

    await service.mark_running(operation.id)
    await service.append_log(operation.id, "Loading template", progress=35)
    await service.fail(operation.id, "Provider unavailable")
    failed = await service.get(operation.id, with_logs=True)
    assert failed.status == OperationStatus.FAILED
    assert failed.progress == 35
    assert failed.error_message == "Provider unavailable"
    assert [item.sequence for item in failed.logs] == sorted(item.sequence for item in failed.logs)
    assert any(item.level == "error" for item in failed.logs)

    retry = await service.clone_for_retry(operation.id, "second-admin")
    assert retry.retry_of_id == operation.id
    assert retry.status == OperationStatus.QUEUED

    interrupted = await service.create(
        operation_type="import_repository",
        title="Interrupted import",
        requested_by="admin-user",
    )
    await service.mark_running(interrupted.id)
    queued = await service.recover()
    assert retry.id in queued
    recovered = await service.get(interrupted.id)
    assert recovered.status == OperationStatus.FAILED
    assert "restart" in (recovered.error_message or "")

    await engine.dispose()


@pytest.mark.asyncio
async def test_tag_filter_matches_exact_topic_without_server_error(tmp_path: Path) -> None:
    engine, session_factory = await _database(tmp_path, "tag-filter.db")
    async with session_factory() as session:
        category = Category(name="Portfolio", slug="portfolio", is_active=True)
        provider = Provider(
            name="Community", slug="community", provider_type="community", is_active=True
        )
        framework = Framework(name="Astro", slug="astro", is_active=True)
        session.add_all([category, provider, framework])
        session.add(
            Template(
                name="Astro Test",
                slug="astro-test",
                repository_url="https://github.com/example/astro-test",
                repository_adapter="github",
                default_branch="main",
                topics=["astro", "portfolio"],
                screenshots=[],
                manifest={
                    "schema_version": "2.0",
                    "name": "Astro Test",
                    "framework": "astro",
                    "repository": "https://github.com/example/astro-test",
                    "branch": "main",
                    "deploy": {"type": "static"},
                    "environment": [],
                },
                analysis={},
                quality_breakdown={},
                status=TemplateStatus.PUBLISHED,
                category=category,
                provider=provider,
                framework=framework,
            )
        )
        await session.commit()

    async with session_factory() as session:
        rows, total, _pages = await TemplateService.list_public(
            session,
            page=1,
            page_size=20,
            search=None,
            category=None,
            provider=None,
            framework=None,
            featured=None,
            tag="astro",
        )
        assert total == 1
        assert rows[0].slug == "astro-test"

        rows, total, _pages = await TemplateService.list_public(
            session,
            page=1,
            page_size=20,
            search=None,
            category=None,
            provider=None,
            framework=None,
            featured=None,
            tag="ast",
        )
        assert rows == []
        assert total == 0

    await engine.dispose()


def test_operations_console_and_settings_pages_render(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'admin-views.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///unused.db",
        session_secret=SecretStr("admin-view-test-secret-with-more-than-32-characters"),
    )
    runtime = RuntimeSettingsService(session_factory, settings)
    operation_service = OperationService(session_factory)

    async def prepare() -> AdminOperation:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await runtime.initialize()
        operation = await operation_service.create(
            operation_type="sync_templates",
            title="Live operation test",
            requested_by="admin-user",
            return_url="/admin/template/list",
        )
        await operation_service.append_log(operation.id, "Scanning source", progress=25)
        return operation

    operation = asyncio.run(prepare())
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="admin-route-session-secret")

    @app.middleware("http")
    async def add_identity(request, call_next):
        request.state.admin_identity = SimpleNamespace(subject="admin-user")
        return await call_next(request)

    reload_calls: list[bool] = []

    async def reload_runtime() -> None:
        reload_calls.append(True)

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
        operations = client.get("/admin/operations")
        assert operations.status_code == 200
        assert "Live operation test" in operations.text

        detail = client.get(f"/admin/operations/{operation.id}")
        assert detail.status_code == 200
        assert "Scanning source" in detail.text
        assert "Copy logs" in detail.text

        status = client.get(f"/admin/operations/{operation.id}/status")
        assert status.status_code == 200
        assert status.json()["progress"] == 25

        exported = client.get(f"/admin/operations/{operation.id}/logs.txt")
        assert exported.status_code == 200
        assert "Scanning source" in exported.text

        settings_page = client.get("/admin/settings")
        assert settings_page.status_code == 200
        assert "RegHub Settings" in settings_page.text
        assert "Operations Console" in settings_page.text
        assert "GitHub" in settings_page.text
        assert "Add custom third-party API" in settings_page.text
        token_match = re.search(r'name="csrf_token" value="([^"]+)"', settings_page.text)
        assert token_match is not None
        csrf_token = token_match.group(1)
        feature_rows = asyncio.run(runtime.feature_rows())
        form: dict[str, str] = {
            "csrf_token": csrf_token,
            "action": "save_features",
        }
        for feature in feature_rows:
            form[f"enabled__{feature.key}"] = "1" if feature.enabled else "0"
            form[f"task__{feature.key}"] = "1" if feature.admin_task_allowed else "0"
        form["enabled__ai_metadata"] = "1"
        form["task__ai_metadata"] = "1"
        saved = client.post("/admin/settings", data=form)
        assert saved.status_code == 200
        assert "Feature controls updated immediately" in saved.text
        assert runtime.feature_enabled("ai_metadata", task=True) is True
        assert reload_calls == [True]

    asyncio.run(engine.dispose())


def test_template_action_queues_operation_and_opens_progress_page(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'admin-action.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    operation_service = OperationService(session_factory)
    queued: list[object] = []

    async def prepare() -> Template:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            framework = Framework(name="Astro", slug="astro", is_active=True)
            template = Template(
                name="Action Test",
                slug="action-test",
                repository_url="https://github.com/example/action-test",
                repository_adapter="github",
                default_branch="main",
                topics=["astro"],
                screenshots=[],
                manifest={
                    "schema_version": "2.0",
                    "name": "Action Test",
                    "framework": "astro",
                    "repository": "https://github.com/example/action-test",
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
            await session.commit()
            await session.refresh(template)
            return template

    template = asyncio.run(prepare())
    app = FastAPI()

    @app.middleware("http")
    async def add_identity(request, call_next):
        request.state.admin_identity = SimpleNamespace(subject="admin-user")
        return await call_next(request)

    app.state.container = SimpleNamespace(
        operation_service=operation_service,
        operation_runner=SimpleNamespace(enqueue=queued.append),
        require_feature=lambda *_args, **_kwargs: None,
    )
    admin = Admin(app=app, engine=engine, base_url="/admin", templates_dir="templates")
    admin.add_view(TemplateAdmin)

    with TestClient(app, follow_redirects=False) as client:
        response = client.get(
            "/admin/template/action/sync-source",
            params={
                "pks": str(template.id),
                "return_url": f"/admin/template/details/{template.id}",
            },
        )
        assert response.status_code == 302
        assert response.headers["location"].startswith("/admin/operations/")

    async def inspect_operation() -> None:
        async with session_factory() as session:
            operation = await session.scalar(select(AdminOperation))
            assert operation is not None
            assert operation.operation_type == "sync_templates"
            assert operation.input_payload == {"template_ids": [str(template.id)]}
            assert operation.return_url == f"/admin/template/details/{template.id}"
            assert queued == [operation.id]

    asyncio.run(inspect_operation())
    asyncio.run(engine.dispose())


def test_postgresql_tag_filter_compiles_to_jsonb_containment() -> None:
    from sqlalchemy import cast, select
    from sqlalchemy.dialects.postgresql import JSONB, dialect

    statement = select(Template.id).where(Template.topics.op("@>")(cast(["astro"], JSONB)))
    compiled = str(statement.compile(dialect=dialect()))
    assert "topics @>" in compiled
    assert "JSONB" in compiled


@pytest.mark.asyncio
async def test_operation_runner_executes_publication_with_result_and_logs(tmp_path: Path) -> None:
    from app.operations.service import OperationRunner

    engine, session_factory = await _database(tmp_path, "operation-runner.db")
    async with session_factory() as session:
        category = Category(name="Portfolio", slug="portfolio", is_active=True)
        provider = Provider(
            name="Example", slug="github-example", provider_type="organization", is_active=True
        )
        framework = Framework(name="Astro", slug="astro", is_active=True)
        template = Template(
            name="Publish Test",
            slug="publish-test",
            short_description="Publish-ready template",
            repository_url="https://github.com/example/publish-test",
            repository_adapter="github",
            default_branch="main",
            topics=["astro"],
            screenshots=[],
            manifest={
                "schema_version": "2.0",
                "name": "Publish Test",
                "framework": "astro",
                "repository": "https://github.com/example/publish-test",
                "branch": "main",
                "build": {"command": "npm run build"},
                "deploy": {"type": "static"},
                "environment": [],
            },
            analysis={},
            quality_breakdown={},
            status=TemplateStatus.DRAFT,
            category=category,
            provider=provider,
            framework=framework,
        )
        session.add(template)
        await session.commit()
        await session.refresh(template)
        template_id = template.id

    service = OperationService(session_factory)
    runner = OperationRunner(service)
    runner.bind(
        SimpleNamespace(
            require_feature=lambda *_args, **_kwargs: None,
            session_factory=session_factory,
        )
    )
    operation = await service.create(
        operation_type="set_template_status",
        title="Publish template",
        requested_by="admin-user",
        input_payload={
            "template_ids": [str(template_id)],
            "status": TemplateStatus.PUBLISHED.value,
        },
    )
    await runner._execute(operation.id)

    completed = await service.get(operation.id, with_logs=True)
    assert completed.status == OperationStatus.SUCCEEDED
    assert completed.progress == 100
    assert completed.result_payload == {"updated": 1, "status": "published"}
    assert any("Updated 1 template" in item.message for item in completed.logs)

    async with session_factory() as session:
        published = await session.get(Template, template_id)
        assert published is not None
        assert published.status == TemplateStatus.PUBLISHED
        assert published.published_at is not None

    await engine.dispose()


@pytest.mark.asyncio
async def test_application_container_reloads_provider_settings_without_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.container as container_module

    engine, session_factory = await _database(tmp_path, "container-runtime.db")
    monkeypatch.setattr(container_module, "async_session_factory", session_factory)
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///unused.db",
        session_secret=SecretStr("container-runtime-secret-with-more-than-32-characters"),
        github_token=SecretStr("environment-token"),
    )
    container = container_module.ApplicationContainer(settings)
    await container.initialize()
    assert "github" in container.adapter_names
    assert container.github_authenticated is True

    await container.runtime_settings.upsert_integration(
        slug="github",
        name="GitHub",
        integration_type="source_provider",
        enabled=False,
        base_url=None,
        username=None,
        secret=None,
        clear_secret=True,
        use_environment_fallback=False,
        config={"timeout": 15, "allow_private": False},
        updated_by="admin-user",
    )
    await container.reload_runtime()
    assert "github" not in container.adapter_names
    assert container.github_authenticated is False

    await container.runtime_settings.upsert_integration(
        slug="github",
        name="GitHub",
        integration_type="source_provider",
        enabled=True,
        base_url=None,
        username=None,
        secret="new-runtime-token",
        clear_secret=False,
        use_environment_fallback=False,
        config={"timeout": 15, "allow_private": False},
        updated_by="admin-user",
    )
    await container.reload_runtime()
    assert "github" in container.adapter_names
    assert container.github_authenticated is True

    await container.close()
    await engine.dispose()


def test_disabled_public_api_returns_structured_503_with_request_id() -> None:
    from app.api.errors import registry_error_handler
    from app.core.exceptions import FeatureDisabledError

    request = SimpleNamespace(state=SimpleNamespace(request_id="request-123"))
    response = registry_error_handler(request, FeatureDisabledError("Public API is disabled"))
    assert response.status_code == 503
    assert b'"request_id":"request-123"' in response.body
    assert b'"type":"FeatureDisabledError"' in response.body
