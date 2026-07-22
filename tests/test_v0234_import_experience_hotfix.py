from __future__ import annotations

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqladmin import Admin
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.middleware.sessions import SessionMiddleware

from app.admin.views import OperationsConsoleView
from app.core.enums import OperationStatus, TemplateStatus
from app.database.base import Base
from app.models.category import Category
from app.models.framework import Framework
from app.models.provider import Provider
from app.models.template import Template
from app.operations.service import OperationService
from tests.support import super_admin_identity


class _Runner:
    def __init__(self) -> None:
        self.enqueued: list[UUID] = []

    async def enqueue(self, operation_id: UUID) -> None:
        self.enqueued.append(operation_id)


async def _prepare(session_factory, operation_service: OperationService):
    async with session_factory() as session:
        category = Category(name="Portfolio", slug="portfolio", is_active=True)
        provider = Provider(
            name="Example Studio",
            slug="github-example-studio",
            provider_type="organization",
            website_url="https://github.com/example-studio",
            is_active=True,
        )
        framework = Framework(name="Astro", slug="astro", is_active=True)
        template = Template(
            name="Aurora Portfolio",
            slug="aurora-portfolio",
            short_description="A polished Astro portfolio starter.",
            repository_url="https://github.com/example-studio/aurora",
            repository_adapter="github",
            external_repository_id="example-studio/aurora",
            default_branch="main",
            thumbnail_url="https://cdn.example.com/aurora.webp",
            screenshots=["https://cdn.example.com/aurora.webp"],
            quality_score=94,
            framework_version="5.1.0",
            status=TemplateStatus.DRAFT,
            category=category,
            provider=provider,
            framework=framework,
        )
        session.add(template)
        await session.commit()
        await session.refresh(template)
        template_id = template.id

    duplicate = await operation_service.create(
        operation_type="import_repository",
        title="Import GitHub repository",
        requested_by="admin-user",
        input_payload={
            "adapter": "github",
            "repository_url": "https://github.com/example-studio/aurora",
        },
        return_url="/admin/github-import",
    )
    await operation_service.mark_running(duplicate.id)
    await operation_service.skip(
        duplicate.id,
        "Already imported",
        {
            "outcome": "already_exists",
            "template_id": str(template_id),
            "template_slug": "aurora-portfolio",
            "template_name": "Aurora Portfolio",
            "template_url": f"/admin/template/details/{template_id}",
        },
    )
    return template_id, duplicate


def test_duplicate_import_renders_template_card_and_continue_update(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'import-hotfix.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    operation_service = OperationService(session_factory)

    async def prepare():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        return await _prepare(session_factory, operation_service)

    template_id, duplicate = asyncio.run(prepare())
    runner = _Runner()

    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="import-experience-hotfix-session")

    @app.middleware("http")
    async def add_identity(request, call_next):
        request.state.admin_identity = super_admin_identity()
        return await call_next(request)

    app.state.container = SimpleNamespace(
        operation_service=operation_service,
        operation_runner=runner,
        session_factory=session_factory,
        feature_enabled=lambda *_args, **_kwargs: True,
    )
    admin = Admin(app=app, engine=engine, base_url="/admin", templates_dir="templates")
    admin.add_view(OperationsConsoleView)

    with TestClient(app, follow_redirects=False) as client:
        detail = client.get(f"/admin/operations/{duplicate.id}")
        assert detail.status_code == 200
        assert "Already found!" in detail.text
        assert "Continue to update template" in detail.text
        assert "Aurora Portfolio" in detail.text
        assert "A polished Astro portfolio starter." in detail.text
        assert "Example Studio" in detail.text
        assert "Portfolio" in detail.text
        assert "https://cdn.example.com/aurora.webp" in detail.text
        assert f"/admin/template/details/{template_id}" in detail.text
        assert "View template" in detail.text

        status = client.get(f"/admin/operations/{duplicate.id}/status")
        assert status.status_code == 200
        payload = status.json()
        assert payload["status"] == "skipped"
        assert payload["template"]["name"] == "Aurora Portfolio"
        assert payload["template"]["quality_score"] == 94

        csrf = re.search(r'name="csrf_token" value="([^"]+)"', detail.text)
        assert csrf is not None
        continued = client.post(
            f"/admin/operations/{duplicate.id}/continue-update",
            data={"csrf_token": csrf.group(1)},
        )
        assert continued.status_code == 302
        assert continued.headers["location"].startswith("/admin/operations/")
        new_id = UUID(continued.headers["location"].rsplit("/", 1)[-1])
        assert runner.enqueued == [new_id]

    async def verify_update_operation() -> None:
        operation = await operation_service.get(new_id)
        assert operation.status == OperationStatus.QUEUED
        assert operation.operation_type == "sync_templates"
        assert operation.input_payload == {"template_ids": [str(template_id)]}
        assert operation.return_url == f"/admin/template/details/{template_id}"
        assert operation.retry_of_id == duplicate.id

    asyncio.run(verify_update_operation())
    asyncio.run(engine.dispose())


def test_operation_template_card_markup_and_dynamic_view_button_exist() -> None:
    root = Path(__file__).parents[1]
    detail = (root / "templates" / "operation_detail.html").read_text()
    layout = (root / "templates" / "reghub_layout.html").read_text()
    views = (root / "app" / "admin" / "views.py").read_text()

    assert 'id="viewTemplateButton"' in detail
    assert 'id="templateSummaryBlock"' in detail
    assert 'id="continueUpdateForm"' in detail
    assert "Already found!" in detail
    assert "Continue to update template" in detail
    assert "renderTemplate(data.template" in detail
    assert "/continue-update" in views
    assert "_operation_template_summary" in views
    assert ".reghub-template-preview" in layout


def test_single_template_sync_result_keeps_template_context(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sync-context.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    service = OperationService(session_factory)
    template_id = UUID("39ed4d46-85bb-4e34-85bb-4e3485bb4e34")

    class _SyncService:
        async def sync_one(self, identifier, requested_by=None, progress=None):
            assert identifier == template_id
            assert requested_by == "admin-user"
            if progress:
                await progress(50, "Source metadata refreshed", "debug")
            return SimpleNamespace(
                id=template_id,
                slug="aurora-portfolio",
                name="Aurora Portfolio",
                status=TemplateStatus.PUBLISHED,
            )

    async def run() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        operation = await service.create(
            operation_type="sync_templates",
            title="Update imported template: Aurora Portfolio",
            requested_by="admin-user",
            input_payload={"template_ids": [str(template_id)]},
        )
        from app.operations.service import OperationRunner

        runner = OperationRunner(service)
        runner.bind(
            SimpleNamespace(
                require_feature=lambda *_args, **_kwargs: None,
                template_sync_service=_SyncService(),
            )
        )
        await runner._execute(operation.id)
        finished = await service.get(operation.id)
        assert finished.status == OperationStatus.SUCCEEDED
        assert finished.result_payload["template_id"] == str(template_id)
        assert finished.result_payload["template_slug"] == "aurora-portfolio"
        assert finished.result_payload["template_name"] == "Aurora Portfolio"
        assert finished.result_payload["status"] == "published"

    asyncio.run(run())
    asyncio.run(engine.dispose())
