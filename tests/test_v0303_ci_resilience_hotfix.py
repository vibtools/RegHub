from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import TypeAdapter
from starlette.requests import Request
from starlette.responses import Response

from app.api.v1.catalog import _cache_get, _cache_set
from app.operations.service import OperationRunner


class _OperationServiceStub:
    def __init__(self) -> None:
        self.logs: list[dict[str, object]] = []

    async def append_log(self, operation_id, message, **kwargs) -> None:
        self.logs.append(
            {
                "operation_id": operation_id,
                "message": message,
                **kwargs,
            }
        )


class _FailingAudit:
    async def append(self, **_kwargs) -> None:
        raise RuntimeError("audit backend unavailable")


class _FailingCache:
    async def get_json(self, _key):
        raise ConnectionError("cache read unavailable")

    async def set_json(self, _key, _value) -> None:
        raise ConnectionError("cache write unavailable")

    async def invalidate_all(self) -> None:
        raise ConnectionError("cache invalidation unavailable")


def _request(container: object) -> Request:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "path": "/api/v1/test",
            "raw_path": b"/api/v1/test",
            "query_string": b"",
            "headers": [(b"host", b"testserver")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 443),
            "app": SimpleNamespace(state=SimpleNamespace(container=container)),
        }
    )
    request.state.request_id = "cache-resilience-test"
    return request


@pytest.mark.asyncio
async def test_catalog_cache_is_optional_and_fail_open() -> None:
    adapter = TypeAdapter(dict[str, str])
    response = Response()
    request = _request(SimpleNamespace())

    assert await _cache_get(request, response, "test", adapter) is None
    assert response.headers["X-RegHub-Cache"] == "BYPASS"
    await _cache_set(request, "test", adapter, {"status": "ok"})

    failing_response = Response()
    failing_request = _request(SimpleNamespace(catalog_cache=_FailingCache()))
    assert await _cache_get(failing_request, failing_response, "test", adapter) is None
    assert failing_response.headers["X-RegHub-Cache"] == "BYPASS"
    await _cache_set(failing_request, "test", adapter, {"status": "ok"})


@pytest.mark.asyncio
async def test_terminal_side_effect_failures_do_not_rewrite_operation_outcome() -> None:
    service = _OperationServiceStub()
    runner = OperationRunner(service)  # type: ignore[arg-type]
    runner.bind(SimpleNamespace(audit=_FailingAudit(), catalog_cache=_FailingCache()))
    operation = SimpleNamespace(
        id=uuid4(),
        operation_type="sync_templates",
        title="Resilience test",
        requested_by="admin-user",
        requested_roles=["super_admin"],
    )

    await runner._audit_terminal(  # type: ignore[arg-type]
        operation,
        outcome="succeeded",
        result={"synced": 1},
    )

    messages = [str(item["message"]) for item in service.logs]
    assert "Governance audit append failed after operation completion" in messages
    assert "Catalog cache invalidation failed; database result remains authoritative" in messages
