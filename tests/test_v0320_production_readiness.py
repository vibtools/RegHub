import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError

from app import __version__
from app.core.config import Settings
from app.core.exceptions import ValidationError as RegistryValidationError
from app.core.middleware import normalize_request_id
from app.infrastructure.proxy import TrustedProxyHeadersMiddleware, _validated_forwarded_host
from app.registry.local import repository_from_manifest, repository_from_zip

ROOT = Path(__file__).resolve().parents[1]


def production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "production",
        "database_url": "postgresql+asyncpg://reghub:password@postgres:5432/reghub",
        "session_secret": SecretStr("session-" + "s" * 64),
        "runtime_encryption_key": SecretStr("runtime-" + "r" * 64),
        "audit_signing_key": SecretStr("audit-" + "a" * 64),
        "session_cookie_secure": True,
        "public_base_url": "https://reghub.ygit.dev",
        "allowed_hosts": ["reghub.ygit.dev"],
        "oidc_issuer_url": "https://auth.vib.tools/realms/vib",
        "oidc_client_id": "reghub",
        "oidc_client_secret": SecretStr("oidc-client-secret"),
        "trusted_proxy_networks": ["10.0.0.0/8"],
    }
    values.update(overrides)
    return Settings(**values)


def make_zip(files: list[tuple[str, bytes]]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files:
            archive.writestr(name, data)
    return output.getvalue()


def test_v0320_version_and_hidden_release_files_are_consistent() -> None:
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert __version__ == "0.3.2.0"
    assert 'version = "0.3.2.0"' in project
    for relative in (".gitignore", ".dockerignore", ".env.example", ".github/workflows/ci.yml"):
        assert (ROOT / relative).is_file()


def test_production_requires_independent_keys_and_secure_origins() -> None:
    assert production_settings().app_env == "production"
    with pytest.raises(ValidationError, match="RUNTIME_ENCRYPTION_KEY"):
        production_settings(runtime_encryption_key=None)
    with pytest.raises(ValidationError, match="AUDIT_SIGNING_KEY"):
        production_settings(audit_signing_key=None)
    with pytest.raises(ValidationError, match="must differ"):
        production_settings(audit_signing_key=SecretStr("runtime-" + "r" * 64))
    with pytest.raises(ValidationError, match=r"postgresql\+asyncpg"):
        production_settings(database_url="sqlite:///tmp/reghub.db")
    with pytest.raises(ValidationError, match="host must be present"):
        production_settings(public_base_url="https://other.example")
    with pytest.raises(ValidationError, match="origin without a path"):
        production_settings(public_base_url="https://reghub.ygit.dev/subpath")


def test_production_validates_optional_credential_endpoints() -> None:
    with pytest.raises(ValidationError, match="AI_BASE_URL must use HTTPS"):
        production_settings(ai_base_url="http://ai.example", ai_api_key=SecretStr("token"))
    with pytest.raises(ValidationError, match="AI_BASE_URL and AI_API_KEY"):
        production_settings(ai_metadata_enabled=True)
    with pytest.raises(ValidationError, match="GITHUB_TOKEN"):
        production_settings(github_allow_private_repositories=True)
    with pytest.raises(ValidationError, match="configured together"):
        production_settings(bitbucket_username="user")
    with pytest.raises(ValidationError, match="embedded credentials"):
        production_settings(
            ai_base_url="https://user:password@ai.example",
            ai_api_key=SecretStr("token"),
        )


def test_request_id_rejects_control_characters_and_oversized_values() -> None:
    assert normalize_request_id("request-123") == "request-123"
    assert normalize_request_id("request_123:part") == "request_123:part"
    assert normalize_request_id("bad\nvalue") != "bad\nvalue"
    assert len(normalize_request_id("x" * 129)) == 36


def test_proxy_rejects_invalid_chain_and_forwarded_host() -> None:
    middleware = TrustedProxyHeadersMiddleware(lambda *_args: None, ["10.0.0.0/8"])
    assert middleware._client_from_chain("198.51.100.5, 10.0.0.3", "10.0.0.4") == (
        "198.51.100.5"
    )
    assert middleware._client_from_chain("not-an-ip, 10.0.0.3", "10.0.0.4") == "10.0.0.4"
    assert _validated_forwarded_host("reghub.ygit.dev") == "reghub.ygit.dev"
    assert _validated_forwarded_host("evil.example/path") is None
    assert _validated_forwarded_host("user@evil.example") is None


def test_local_manifest_rejects_ssrf_and_credential_urls() -> None:
    with pytest.raises(RegistryValidationError, match="private or reserved"):
        repository_from_manifest({"name": "bad", "repository": "https://127.0.0.1/repo"})
    with pytest.raises(RegistryValidationError, match="credentials"):
        repository_from_manifest(
            {"name": "bad", "repository": "https://user:pass@example.com/repo"}
        )
    with pytest.raises(RegistryValidationError, match="screenshots must be a list"):
        repository_from_manifest({"name": "bad", "screenshots": "https://example.com/a.png"})


def test_local_manifest_enforces_content_and_collection_bounds() -> None:
    with pytest.raises(RegistryValidationError, match="too many files"):
        repository_from_manifest({"name": "bad", "files": ["x"] * 5001})
    with pytest.raises(RegistryValidationError, match="control characters"):
        repository_from_manifest({"name": "bad", "description": "bad\x01value"})
    with pytest.raises(RegistryValidationError, match="package_json is too large"):
        repository_from_manifest(
            {"name": "bad", "package_json": {"value": "x" * (512 * 1024)}}
        )
    repository = repository_from_manifest(
        {"name": "good", "readme": "first line\nsecond line"}
    )
    assert repository.readme_text == "first line\nsecond line"


def test_local_zip_rejects_case_collisions_and_sanitizes_filename() -> None:
    data = make_zip([("README.md", b"one"), ("readme.md", b"two")])
    with pytest.raises(RegistryValidationError, match="case-colliding"):
        repository_from_zip(data, "bad.zip", max_uncompressed_bytes=10_000, max_entries=10)

    good = make_zip([("starter/package.json", json.dumps({"name": "x"}).encode())])
    repository = repository_from_zip(
        good,
        r"folder\starter.zip",
        max_uncompressed_bytes=10_000,
        max_entries=10,
    )
    assert repository.name == "starter"
    assert repository.metadata["filename"] == "starter.zip"


def test_docker_runtime_uses_installed_wheel_only() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    runtime = dockerfile.split("FROM python:3.13-slim AS runtime", 1)[1]
    assert "reghub==0.3.2.0" in runtime
    assert "COPY app ./app" not in runtime
    assert "USER reghub" in runtime
    assert "site-packages" in runtime


def test_release_helpers_remain_importable() -> None:
    item = SimpleNamespace(metadata={"Name": "RegHub"}, version="0.3.2.0")
    assert item.version == __version__
