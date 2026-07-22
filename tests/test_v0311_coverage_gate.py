import json
import logging
import sys
from typing import Any

import pytest
from pydantic import SecretStr
from starlette.requests import Request
from starlette.responses import Response

from app.auth import oidc as oidc_module
from app.core.config import Settings
from app.core.logging import JsonFormatter, configure_logging
from app.core.middleware import RequestIdMiddleware, SecurityHeadersMiddleware


class FakeOAuth:
    def __init__(self) -> None:
        self.registration: dict[str, Any] | None = None

    def register(self, **kwargs: Any) -> None:
        self.registration = kwargs


def _request(*, scheme: str = "https", request_id: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if request_id:
        headers.append((b"x-request-id", request_id.encode()))

    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": scheme,
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "root_path": "",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 443 if scheme == "https" else 80),
        }
    )


def test_json_logging_and_root_configuration() -> None:
    try:
        raise ValueError("expected logging test error")
    except ValueError:
        record = logging.LogRecord(
            name="reghub.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="operation %s",
            args=("failed",),
            exc_info=sys.exc_info(),
        )

    record.request_id = "request-123"
    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "ERROR"
    assert payload["logger"] == "reghub.test"
    assert payload["message"] == "operation failed"
    assert payload["request_id"] == "request-123"
    assert "ValueError: expected logging test error" in payload["exception"]
    assert payload["timestamp"].endswith("+00:00")

    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        configure_logging("debug")
        assert root.level == logging.DEBUG
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JsonFormatter)
    finally:
        root.handlers.clear()
        root.handlers.extend(original_handlers)
        root.setLevel(original_level)


def test_oidc_registration_uses_existing_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oidc_module, "OAuth", FakeOAuth)

    disabled = oidc_module.build_oauth(Settings(app_env="test"))
    assert isinstance(disabled, FakeOAuth)
    assert disabled.registration is None

    settings = Settings(
        app_env="test",
        oidc_issuer_url="https://auth.example/realms/vib/",
        oidc_client_id="reghub",
        oidc_client_secret=SecretStr("test-client-secret"),
        oidc_scopes="openid profile email roles",
    )
    oauth = oidc_module.build_oauth(settings)

    assert isinstance(oauth, FakeOAuth)
    assert oauth.registration == {
        "name": "vib_auth",
        "client_id": "reghub",
        "client_secret": "test-client-secret",
        "server_metadata_url": ("https://auth.example/realms/vib/.well-known/openid-configuration"),
        "client_kwargs": {
            "scope": "openid profile email roles",
            "code_challenge_method": "S256",
        },
    }


@pytest.mark.asyncio
async def test_request_id_and_security_headers_middleware() -> None:
    async def call_next(_request: Request) -> Response:
        return Response("ok")

    request = _request(request_id="request-456")
    request_id_middleware = RequestIdMiddleware(app=lambda *_args: None)
    response = await request_id_middleware.dispatch(request, call_next)

    assert request.state.request_id == "request-456"
    assert response.headers["X-Request-ID"] == "request-456"

    secure_request = _request(scheme="https")
    security_middleware = SecurityHeadersMiddleware(app=lambda *_args: None)
    secure_response = await security_middleware.dispatch(secure_request, call_next)

    assert secure_response.headers["X-Content-Type-Options"] == "nosniff"
    assert secure_response.headers["X-Frame-Options"] == "DENY"
    assert secure_response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert secure_response.headers["Permissions-Policy"] == (
        "camera=(), microphone=(), geolocation=()"
    )
    assert secure_response.headers["Strict-Transport-Security"] == (
        "max-age=31536000; includeSubDomains"
    )
