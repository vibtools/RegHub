from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import DEVELOPMENT_SESSION_SECRET, Settings
from scripts import audit_requirements, startup, verify_alembic_heads

ROOT = Path(__file__).resolve().parents[1]


def _production_settings(**overrides):
    values = {
        "app_env": "production",
        "session_secret": SecretStr("s" * 64),
        "session_cookie_secure": True,
        "runtime_encryption_key": SecretStr("r" * 64),
        "audit_signing_key": SecretStr("a" * 64),
        "public_base_url": "https://reghub.ygit.dev",
        "allowed_hosts": ["reghub.ygit.dev"],
        "oidc_issuer_url": "https://auth.vib.tools/realms/vib",
        "oidc_client_id": "reghub",
        "oidc_client_secret": SecretStr("oidc-client-secret"),
        "trusted_proxy_networks": ["10.0.0.0/8"],
    }
    values.update(overrides)
    return Settings(**values)


def test_release_version_is_consistent() -> None:
    assert 'version = "0.3.2.0"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "version=__version__" in (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "version=__version__" in (ROOT / "app/api/v1/catalog.py").read_text(encoding="utf-8")


def test_production_rejects_insecure_defaults_and_proxy_trust() -> None:
    with pytest.raises(ValidationError, match="development or example"):
        _production_settings(session_secret=SecretStr(DEVELOPMENT_SESSION_SECRET))
    with pytest.raises(ValidationError, match="PUBLIC_BASE_URL must use HTTPS"):
        _production_settings(public_base_url="http://reghub.ygit.dev")
    with pytest.raises(ValidationError, match="OIDC_ISSUER_URL must use HTTPS"):
        _production_settings(oidc_issuer_url="http://auth.vib.tools/realms/vib")
    with pytest.raises(ValidationError, match="must not contain wildcard"):
        _production_settings(trusted_proxy_networks=["*"])
    assert _production_settings().app_env == "production"


def test_audit_snapshot_is_pinned_sorted_and_excludes_private_package(monkeypatch) -> None:
    fake = [
        SimpleNamespace(metadata={"Name": "Zeta_Package"}, version="2.0"),
        SimpleNamespace(metadata={"Name": "RegHub"}, version="0.3.2.0"),
        SimpleNamespace(metadata={"Name": "alpha.package"}, version="1.4.0"),
    ]
    monkeypatch.setattr(audit_requirements, "distributions", lambda: fake)
    result = audit_requirements.build_requirements(
        excluded={"reghub"},
        required_present={"reghub"},
    )
    assert result == ["alpha-package==1.4.0", "zeta-package==2.0"]


def test_release_delivery_contract_is_hardened() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    entrypoint = (ROOT / "scripts/entrypoint.sh").read_text(encoding="utf-8")
    startup_script = (ROOT / "scripts/startup.py").read_text(encoding="utf-8")

    assert "python -m pip check" in workflow
    assert "python -m scripts.verify_alembic_heads" in workflow
    assert "python -m scripts.audit_requirements" in workflow
    assert "--strict --no-deps --disable-pip" in workflow
    assert "/api/v1/ready" in workflow
    assert "python -m pip check" in dockerfile
    assert "/api/v1/ready" in dockerfile
    assert "python -m scripts.startup" in entrypoint
    assert "pg_try_advisory_lock" in startup_script
    assert "alembic" in startup_script
    assert "scripts.seed" in startup_script


def test_release_helpers_parse_expected_inputs() -> None:
    assert startup.normalize_database_dsn("postgresql+asyncpg://u:p@db/name") == (
        "postgresql://u:p@db/name"
    )
    assert verify_alembic_heads.parse_heads("20260722_0008 (head)\n") == ["20260722_0008 (head)"]


@pytest.mark.asyncio
async def test_startup_serializes_migration_and_seed(monkeypatch) -> None:
    events: list[object] = []

    class FakeConnection:
        async def fetchval(self, statement: str, lock_id: int) -> bool:
            events.append(("lock", statement, lock_id))
            return True

        async def execute(self, statement: str, lock_id: int) -> None:
            events.append(("unlock", statement, lock_id))

        async def close(self) -> None:
            events.append("close")

    async def fake_connect(dsn: str, **kwargs: object):
        events.append(("connect", dsn, kwargs.get("timeout")))
        return FakeConnection()

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db/name")
    monkeypatch.setattr(startup.asyncpg, "connect", fake_connect)
    monkeypatch.setattr(
        startup,
        "run_startup_command",
        lambda *args: events.append(("command", args)),
    )

    await startup.run_startup()

    assert events[0] == ("connect", "postgresql://u:p@db/name", 20)
    assert events[1][0] == "lock"
    assert events[2][0] == "command"
    assert events[2][1][1:] == ("-m", "alembic", "upgrade", "head")
    assert events[3][0] == "command"
    assert events[3][1][1:] == ("-m", "scripts.seed")
    assert events[4][0] == "unlock"
    assert events[5] == "close"


def test_startup_rejects_non_postgresql_database_url() -> None:
    with pytest.raises(ValueError, match="must use PostgreSQL"):
        startup.normalize_database_dsn("sqlite:///tmp/reghub.db")


def test_audit_snapshot_requires_private_distribution(monkeypatch) -> None:
    fake = [SimpleNamespace(metadata={"Name": "FastAPI"}, version="0.139.2")]
    monkeypatch.setattr(audit_requirements, "distributions", lambda: fake)
    with pytest.raises(RuntimeError, match="reghub"):
        audit_requirements.build_requirements(
            excluded={"reghub"},
            required_present={"reghub"},
        )
