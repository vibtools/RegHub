from __future__ import annotations

from pydantic import SecretStr, ValidationError

from app.core.config import Settings


def production_values() -> dict[str, object]:
    return {
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


def require_rejection(field: str, value: object, expected: str) -> None:
    candidate = production_values()
    candidate[field] = value
    try:
        Settings(**candidate)
    except ValidationError as exc:
        if expected not in str(exc):
            raise RuntimeError(f"Unexpected validation error for {field}: {exc}") from exc
        return
    raise RuntimeError(f"Production configuration unexpectedly accepted insecure {field}")


def main() -> int:
    settings = Settings(**production_values())
    if settings.app_env != "production" or settings.base_url != "https://reghub.ygit.dev":
        raise RuntimeError("Secure production settings did not normalize as expected")
    require_rejection("allowed_hosts", ["*"], "ALLOWED_HOSTS")
    require_rejection("trusted_proxy_networks", ["*"], "TRUSTED_PROXY_NETWORKS")
    require_rejection("database_url", "sqlite:///tmp/reghub.db", "postgresql+asyncpg")
    require_rejection("runtime_encryption_key", None, "RUNTIME_ENCRYPTION_KEY")
    require_rejection("audit_signing_key", None, "AUDIT_SIGNING_KEY")
    require_rejection("public_base_url", "http://reghub.ygit.dev", "HTTPS")
    print("Production configuration validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
