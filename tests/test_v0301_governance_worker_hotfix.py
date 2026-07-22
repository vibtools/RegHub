from pathlib import Path
from typing import Any

import sys
import types

import pytest

# The sandbox image does not ship python-slugify. A minimal import stub keeps
# this isolated infrastructure regression test independent from that optional
# runtime dependency; the production package still declares python-slugify.
_slugify = types.ModuleType("slugify")
_slugify.slugify = lambda value: str(value).strip().lower().replace(" ", "-")
sys.modules.setdefault("slugify", _slugify)

from app.core.config import Settings
from app.core.exceptions import ValidationError
from app.operations.service import OperationRunner
from app.runtime.settings import RuntimeSettingsService


def test_governance_uses_shared_responsive_layout_block():
    source = Path("templates/governance.html").read_text(encoding="utf-8")
    assert '{% extends "reghub_layout.html" %}' in source
    assert "{% block reghub_content %}" in source
    assert "{% block content %}" not in source
    assert "reghub-section-stack" in source
    assert "reghub-status-grid" in source


def test_redis_worker_feature_is_runtime_controlled_and_backward_compatible():
    inprocess = RuntimeSettingsService._build_definitions(Settings(app_env="development"))
    redis_mode = RuntimeSettingsService._build_definitions(
        Settings(app_env="development", operation_backend="redis", redis_url="redis://localhost")
    )
    inprocess_worker = next(item for item in inprocess if item.key == "redis_worker")
    redis_worker = next(item for item in redis_mode if item.key == "redis_worker")
    assert inprocess_worker.category == "Operations"
    assert not inprocess_worker.enabled
    assert redis_worker.enabled
    assert "standalone worker" in inprocess_worker.description


class _QueueStub:
    def __init__(self, status: dict[str, Any] | None = None) -> None:
        self.initialized = False
        self.status = status

    async def initialize(self) -> None:
        self.initialized = True

    async def worker_status(self) -> dict[str, Any] | None:
        return self.status


@pytest.mark.asyncio
async def test_runtime_worker_activation_requires_redis_and_heartbeat():
    runner = OperationRunner(None, backend="inprocess", redis_url=None)  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="REDIS_URL"):
        await runner.set_redis_worker_enabled(True)

    runner._queue = _QueueStub(None)  # type: ignore[assignment]  # noqa: SLF001
    with pytest.raises(ValidationError, match="heartbeat"):
        await runner.set_redis_worker_enabled(True, verify_worker=True)
    assert not runner.redis_worker_enabled

    runner._queue = _QueueStub(  # type: ignore[assignment]  # noqa: SLF001
        {"worker_id": "worker-1", "status": "idle", "queue_depth": 0}
    )
    runner._queue_initialized = False  # noqa: SLF001
    await runner.set_redis_worker_enabled(True, verify_worker=True)
    assert runner.redis_worker_enabled
    assert runner.effective_backend == "redis"
    await runner.set_redis_worker_enabled(False)
    assert runner.effective_backend == "inprocess"


def test_health_and_capabilities_report_effective_backend():
    health_source = Path("app/api/v1/health.py").read_text(encoding="utf-8")
    catalog_source = Path("app/api/v1/catalog.py").read_text(encoding="utf-8")
    assert "container.operation_runner.effective_backend" in health_source
    assert "container.operation_runner.redis_worker_enabled" in health_source
    assert "container.operation_runner.effective_backend" in catalog_source
