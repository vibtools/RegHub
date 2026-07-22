import base64
import hashlib

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.security import AdminIdentity, AdminTokenSigner
from app.database.base import Base
from app.governance.audit import AuditService
from app.governance.rbac import has_permission, resolve_roles
from app.infrastructure.cache import CatalogCacheService
from app.infrastructure.proxy import TrustedProxyHeadersMiddleware
from app.infrastructure.rate_limit import RateLimitService
from app.models.audit_event import AuditChainState, AuditEvent
from app.runtime.settings import SecretCipher


def test_rbac_preserves_legacy_admin_and_maps_granular_roles():
    settings = Settings(app_env="development")
    assert resolve_roles({"roles": ["reghub-admin"]}, settings) == ("super_admin",)
    roles = resolve_roles({"roles": ["reghub-editor", "reghub-publisher"]}, settings)
    identity = AdminIdentity("sub", None, None, {}, roles)
    assert has_permission(identity, "templates.write")
    assert has_permission(identity, "publication.manage")
    assert has_permission(identity, "operations.run")
    assert not has_permission(identity, "settings.manage")


def test_old_admin_cookie_never_defaults_to_super_admin():
    signer = AdminTokenSigner("x" * 40)
    token = signer._serializer.dumps(
        {"subject": "legacy", "email": None, "name": None, "claims": {}}
    )
    identity = signer.verify(token, 60)
    assert identity is None


def test_secret_cipher_reads_v1_and_writes_versioned_v2():
    old_key = "old-runtime-key"
    digest = hashlib.sha256(("reghub-runtime-settings-v1:" + old_key).encode()).digest()
    legacy = Fernet(base64.urlsafe_b64encode(digest))
    legacy_value = "fernet:v1:" + legacy.encrypt(b"secret-value").decode()

    cipher = SecretCipher(["new-runtime-key", old_key])
    assert cipher.decrypt(legacy_value) == "secret-value"
    encrypted = cipher.encrypt("next-secret")
    assert encrypted.startswith(f"fernet:v2:{cipher.primary_key_id}:")
    assert cipher.decrypt(encrypted) == "next-secret"


@pytest.mark.asyncio
async def test_memory_cache_generation_invalidation():
    cache = CatalogCacheService(backend="memory", redis_url=None, ttl_seconds=60)
    await cache.initialize()
    await cache.set_json("catalog", {"value": 1})
    assert await cache.get_json("catalog") == {"value": 1}
    await cache.invalidate_all()
    assert await cache.get_json("catalog") is None


@pytest.mark.asyncio
async def test_memory_rate_limiter_enforces_fixed_window():
    limiter = RateLimitService(backend="memory", redis_url=None)
    await limiter.initialize()
    assert (await limiter.check("public", "client", 2)).allowed
    assert (await limiter.check("public", "client", 2)).allowed
    third = await limiter.check("public", "client", 2)
    assert not third.allowed
    assert third.remaining == 0


@pytest.mark.asyncio
async def test_trusted_proxy_headers_ignore_untrusted_peer():
    captured = {}

    async def app(scope, receive, send):
        captured.update(
            client=scope.get("client"),
            scheme=scope.get("scheme"),
            headers=dict(scope.get("headers", [])),
        )
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = TrustedProxyHeadersMiddleware(app, ["10.0.0.0/8"])
    messages = iter([{"type": "http.request", "body": b"", "more_body": False}])

    async def receive():
        return next(messages)

    async def send(_message):
        return None

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "GET",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "scheme": "http",
        "client": ("203.0.113.9", 5000),
        "server": ("localhost", 80),
        "headers": [(b"x-forwarded-for", b"198.51.100.5"), (b"host", b"localhost")],
    }
    await middleware(scope, receive, send)
    assert captured["client"][0] == "203.0.113.9"


@pytest.mark.asyncio
async def test_trusted_proxy_headers_normalize_trusted_chain():
    captured = {}

    async def app(scope, receive, send):
        captured.update(client=scope.get("client"), scheme=scope.get("scheme"))
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = TrustedProxyHeadersMiddleware(app, ["10.0.0.0/8"])

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "GET",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "scheme": "http",
        "client": ("10.0.0.4", 5000),
        "server": ("localhost", 80),
        "headers": [
            (b"x-forwarded-for", b"198.51.100.5, 10.0.0.3"),
            (b"x-forwarded-proto", b"https"),
            (b"host", b"localhost"),
        ],
    }
    await middleware(scope, receive, send)
    assert captured["client"][0] == "198.51.100.5"
    assert captured["scheme"] == "https"


def test_audit_details_redact_nested_credentials_and_key_rotation():
    audit = AuditService(None, ["new-audit-key", "old-audit-key"])  # type: ignore[arg-type]
    safe = audit._safe_details(
        {
            "provider": {"api_token": "should-not-appear", "name": "GitHub"},
            "items": [{"password": "hidden", "value": "safe"}],
        }
    )
    assert safe["provider"]["api_token"] == "[REDACTED]"
    assert safe["items"][0]["password"] == "[REDACTED]"
    assert len(audit.primary_key_id) == 12


@pytest.mark.asyncio
async def test_audit_chain_detects_tampering(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'audit.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[AuditChainState.__table__, AuditEvent.__table__],
            )
        )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    audit = AuditService(sessions, ["audit-signing-key", "previous-audit-key"])
    identity = AdminIdentity("admin", "admin@example.com", "Admin", {}, ("super_admin",))
    await audit.append(
        action="settings.update",
        resource_type="settings",
        identity=identity,
        details={"feature": "cache"},
    )
    await audit.append(
        action="template.publish",
        resource_type="template",
        resource_id="abc",
        actor_subject="admin",
    )
    valid = await audit.verify()
    assert valid.valid
    assert valid.checked == 2
    assert valid.total == 2
    assert valid.complete

    async with sessions() as session:
        await session.execute(
            update(AuditEvent).where(AuditEvent.sequence == 1).values(action="tampered")
        )
        await session.commit()
    invalid = await audit.verify()
    assert not invalid.valid
    assert invalid.first_invalid_sequence == 1

    async with sessions() as session:
        await session.execute(
            update(AuditEvent).where(AuditEvent.sequence == 1).values(action="settings.update")
        )
        await session.commit()
    assert (await audit.verify()).valid

    async with sessions() as session:
        await session.execute(delete(AuditEvent).where(AuditEvent.sequence == 2))
        await session.commit()
    tail_deleted = await audit.verify()
    assert not tail_deleted.valid
    assert "event tail" in tail_deleted.message
    await engine.dispose()
