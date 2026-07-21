from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.core.enums import ImportStatus, OperationStatus
from app.core.exceptions import AuthorizationError, DuplicateTemplateError
from app.database.base import Base
from app.models.api_access import ApiBlockRule, ApiServiceToken
from app.models.category import Category
from app.models.framework import Framework
from app.models.import_history import ImportHistory
from app.models.provider import Provider
from app.models.template import Template
from app.operations.service import OperationRunner, OperationService
from app.registry.adapters.base import ImportedRepository, RegistryAdapter
from app.registry.adapters.registry import AdapterRegistry
from app.registry.template import TemplateImportService
from app.runtime.api_access import ApiAccessService


async def _database(tmp_path: Path, name: str):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / name}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, session_factory


def _request(
    *,
    token: str | None = None,
    client_ip: str = "203.0.113.25",
    hostname: str = "reghub.example.com",
) -> Request:
    headers: list[tuple[bytes, bytes]] = [(b"host", hostname.encode())]
    if token:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "path": "/api/v1/templates",
            "raw_path": b"/api/v1/templates",
            "query_string": b"",
            "headers": headers,
            "client": (client_ip, 443),
            "server": (hostname, 443),
        }
    )


@pytest.mark.asyncio
async def test_api_access_live_mode_scopes_hashing_and_block_rules(tmp_path: Path) -> None:
    engine, session_factory = await _database(tmp_path, "api-access.db")
    service = ApiAccessService(session_factory, "api-access-test-secret-with-adequate-length")
    await service.initialize()
    assert service.mode == "development"
    assert service.normalize_block_rule("localhost") == ("localhost", "hostname")
    assert service.normalize_block_rule("10.x.x.x") == ("10.0.0.0/8", "cidr")
    assert service.normalize_block_rule("172.x.x.x") == ("172.16.0.0/12", "cidr")

    token_row, raw_token = await service.create_token(
        name="YGIT catalog reader",
        scopes=["catalog", "assets"],
        description="Production YGIT registry access",
        expires_at=datetime.now(UTC) + timedelta(days=7),
        created_by="admin-user",
    )
    assert raw_token.startswith("vt_reg_")
    assert raw_token not in token_row.token_hash
    assert token_row.token_prefix in raw_token

    async with session_factory() as session:
        stored = await session.get(ApiServiceToken, token_row.id)
        assert stored is not None
        assert stored.token_hash != raw_token
        assert len(stored.token_hash) == 64

    await service.set_mode("live", "admin-user")
    assert service.live_mode is True

    with pytest.raises(AuthorizationError, match="requires Authorization"):
        await service.authorize(_request(), "catalog")

    await service.authorize(_request(token=raw_token), "catalog")
    with pytest.raises(AuthorizationError, match="does not permit"):
        await service.authorize(_request(token=raw_token), "freshness")

    rule = await service.add_block_rule(
        value="203.0.113.0/24",
        note="Blocked test network",
        created_by="admin-user",
    )
    assert rule.rule_type == "cidr"
    with pytest.raises(AuthorizationError, match="blocked"):
        await service.authorize(_request(token=raw_token), "catalog")

    await service.update_block_rule(
        rule.id,
        value="198.51.100.10",
        enabled=True,
        note="Single address",
        updated_by="admin-user",
    )
    await service.authorize(_request(token=raw_token), "catalog")
    with pytest.raises(AuthorizationError, match="blocked"):
        await service.authorize(_request(token=raw_token, client_ip="198.51.100.10"), "catalog")

    await service.set_token_enabled(token_row.id, False, "admin-user")
    with pytest.raises(AuthorizationError, match="invalid or disabled"):
        await service.authorize(_request(token=raw_token), "catalog")

    await service.set_token_enabled(token_row.id, True, "admin-user")
    await service.delete_block_rule(rule.id)
    await service.authorize(_request(token=raw_token), "assets")

    await service.delete_token(token_row.id)
    assert await service.token_rows() == []
    async with session_factory() as session:
        assert await session.scalar(select(ApiBlockRule)) is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_api_check_token_bypasses_live_policy_temporarily(tmp_path: Path) -> None:
    engine, session_factory = await _database(tmp_path, "api-check-token.db")
    service = ApiAccessService(session_factory, "api-check-test-secret-with-adequate-length")
    await service.initialize()
    _row, raw = await service.create_token(
        name="Bootstrap",
        scopes=["catalog"],
        description=None,
        expires_at=None,
        created_by="admin-user",
    )
    await service.set_mode("live", "admin-user")
    await service.add_block_rule(value="203.0.113.25", note="Test", created_by="admin-user")

    check_token = service.issue_check_token()
    await service.authorize(_request(token=check_token), "capabilities")
    with pytest.raises(AuthorizationError, match="blocked"):
        await service.authorize(_request(token=raw), "catalog")

    await engine.dispose()


class _StaticAdapter(RegistryAdapter):
    name = "github"

    async def import_repository(self, repository_url: str) -> ImportedRepository:
        return ImportedRepository(
            adapter="github",
            external_id="duplicate-repo-1",
            name="Duplicate Repo",
            description="Duplicate import behavior",
            repository_url=repository_url,
            default_branch="main",
            homepage_url=None,
            license_spdx="MIT",
            topics=["astro"],
            primary_language="TypeScript",
            stars_count=2,
            forks_count=1,
            root_files=frozenset({"package.json", "astro.config.mjs"}),
            package_json={"dependencies": {"astro": "5.0.0"}},
            metadata={},
        )


@pytest.mark.asyncio
async def test_duplicate_import_is_successful_no_change_not_failure(tmp_path: Path) -> None:
    engine, session_factory = await _database(tmp_path, "duplicate-import.db")
    async with session_factory() as session:
        session.add_all(
            [
                Framework(name="Unknown", slug="unknown", is_active=True),
                Framework(name="Astro", slug="astro", is_active=True),
                Category(name="General", slug="general", is_active=True),
                Provider(
                    name="Community",
                    slug="community",
                    provider_type="community",
                    is_active=True,
                ),
            ]
        )
        await session.commit()

    service = TemplateImportService(
        session_factory,
        AdapterRegistry([_StaticAdapter()]),
        provider_auto_create_enabled=False,
    )
    repository_url = "https://github.com/example/duplicate-repo"
    first = await service.import_repository(
        repository_url=repository_url,
        requested_by="admin-user",
    )

    with pytest.raises(DuplicateTemplateError) as raised:
        await service.import_repository(
            repository_url=repository_url,
            requested_by="admin-user",
        )
    assert raised.value.template_id == first.id

    async with session_factory() as session:
        histories = list(
            (await session.scalars(select(ImportHistory).order_by(ImportHistory.created_at))).all()
        )
        assert len(histories) == 2
        assert histories[0].status == ImportStatus.SUCCEEDED
        assert histories[1].status == ImportStatus.SUCCEEDED
        assert histories[1].error_message is None
        assert histories[1].metadata_snapshot["outcome"] == "already_exists"
        assert len(list((await session.scalars(select(Template))).all())) == 1

    operation_service = OperationService(session_factory)
    operation = await operation_service.create(
        operation_type="import_repository",
        title="Import duplicate repository",
        requested_by="admin-user",
        input_payload={"adapter": "github", "repository_url": repository_url},
    )
    runner = OperationRunner(operation_service)
    runner.bind(
        SimpleNamespace(
            require_feature=lambda *_args, **_kwargs: None,
            template_import_service=service,
        )
    )
    await runner._execute(operation.id)
    finished = await operation_service.get(operation.id, with_logs=True)
    assert finished.status == OperationStatus.SKIPPED
    assert finished.progress == 100
    assert finished.error_message is None
    assert finished.result_payload["outcome"] == "already_exists"
    assert any("already registered" in row.message for row in finished.logs)

    await engine.dispose()


@pytest.mark.asyncio
async def test_clear_operations_keeps_active_records(tmp_path: Path) -> None:
    engine, session_factory = await _database(tmp_path, "clear-operations.db")
    service = OperationService(session_factory)

    succeeded = await service.create(
        operation_type="sync_templates", title="Done", requested_by="admin"
    )
    await service.mark_running(succeeded.id)
    await service.complete(succeeded.id)

    skipped = await service.create(
        operation_type="import_repository", title="No change", requested_by="admin"
    )
    await service.mark_running(skipped.id)
    await service.skip(skipped.id, "Already registered", {"outcome": "already_exists"})

    queued = await service.create(
        operation_type="sync_templates", title="Still queued", requested_by="admin"
    )
    running = await service.create(
        operation_type="sync_templates", title="Still running", requested_by="admin"
    )
    await service.mark_running(running.id)

    assert await service.clear_terminal("skipped") == 1
    assert (await service.get(queued.id)).status == OperationStatus.QUEUED
    assert (await service.get(running.id)).status == OperationStatus.RUNNING
    assert (await service.get(succeeded.id)).status == OperationStatus.SUCCEEDED

    assert await service.clear_terminal("all_terminal") == 1
    remaining = await service.list_recent()
    assert {item.id for item in remaining} == {queued.id, running.id}

    await engine.dispose()


def test_v023_ui_exposes_productive_controls() -> None:
    root = Path(__file__).parents[1]
    settings = (root / "templates" / "settings.html").read_text()
    operations = (root / "templates" / "operations_list.html").read_text()
    detail = (root / "templates" / "operation_detail.html").read_text()
    gallery = (root / "templates" / "asset_gallery.html").read_text()

    assert "API Manage" in settings
    assert "Development Mode" in settings
    assert "Live Mode" in settings
    assert "vt_reg_" in settings
    assert "Check API endpoints" in settings
    assert "IP, CIDR or hostname" in settings

    assert "Clear history" in operations
    assert 'name="status"' in operations
    assert 'name="type"' in operations
    assert "No change was required" in detail
    assert "Operation logs" in detail
    assert "terminal" in detail.casefold()

    assert "Search templates" in gallery
    assert "Search current gallery" in gallery
    assert 'name="asset_q"' in gallery
