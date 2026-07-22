from __future__ import annotations

import ipaddress
import re
from functools import lru_cache
from typing import Final, Literal
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEVELOPMENT_SESSION_SECRET: Final = "development-secret-change-this-value"  # noqa: S105
_EXAMPLE_SESSION_SECRET: Final = "replace-with-at-least-32-random-characters"  # noqa: S105
_EXAMPLE_RUNTIME_KEY: Final = "replace-with-runtime-encryption-key-at-least-32-chars"  # noqa: S105
_EXAMPLE_AUDIT_KEY: Final = "replace-with-audit-signing-key-at-least-32-chars"  # noqa: S105
_INSECURE_EXAMPLE_SECRETS: Final = frozenset(
    {
        DEVELOPMENT_SESSION_SECRET,
        _EXAMPLE_SESSION_SECRET,
        _EXAMPLE_RUNTIME_KEY,
        _EXAMPLE_AUDIT_KEY,
    }
)
_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def _normalize_allowed_host(value: str) -> str:
    candidate = value.strip().casefold().rstrip(".")
    if not candidate:
        raise ValueError("ALLOWED_HOSTS cannot contain an empty host")
    if candidate == "*":
        return candidate
    if any(character.isspace() or ord(character) < 33 for character in candidate):
        raise ValueError(f"ALLOWED_HOSTS contains an invalid host: {value}")
    if any(token in candidate for token in ("://", "/", "\\", "@", "?", "#")):
        raise ValueError(f"ALLOWED_HOSTS contains an invalid host: {value}")

    host = candidate[2:] if candidate.startswith("*.") else candidate
    if not host:
        raise ValueError(f"ALLOWED_HOSTS contains an invalid host: {value}")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        labels = host.split(".")
        if any(not _HOST_LABEL.fullmatch(label) for label in labels):
            raise ValueError(f"ALLOWED_HOSTS contains an invalid host: {value}") from None
    return candidate


def _host_is_allowed(host: str, allowed_hosts: list[str]) -> bool:
    normalized = host.casefold().rstrip(".")
    for pattern in allowed_hosts:
        if pattern == "*" or pattern == normalized:
            return True
        if pattern.startswith("*.") and normalized.endswith(pattern[1:]):
            return True
    return False


def _secret_value(secret: SecretStr | None) -> str | None:
    if secret is None:
        return None
    value = secret.get_secret_value().strip()
    return value or None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "RegHub"
    app_env: Literal["development", "test", "production"] = "development"
    app_debug: bool = False
    public_base_url: AnyHttpUrl = "http://localhost:8000"
    allowed_hosts: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])
    cors_origins: list[str] = Field(default_factory=list)

    database_url: str = "postgresql+asyncpg://reghub:reghub@localhost:5432/reghub"
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=20, ge=0, le=200)

    session_secret: SecretStr = SecretStr(DEVELOPMENT_SESSION_SECRET)
    session_cookie_secure: bool = False
    session_max_age_seconds: int = Field(default=28_800, ge=300, le=86_400)

    oidc_issuer_url: AnyHttpUrl | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: SecretStr | None = None
    oidc_scopes: str = "openid profile email"
    oidc_admin_claim: str = "roles"
    oidc_admin_values: list[str] = Field(default_factory=lambda: ["reghub-admin"])
    oidc_role_claim: str = "roles"
    oidc_role_values: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "super_admin": ["reghub-admin", "reghub-super-admin"],
            "security_admin": ["reghub-security-admin"],
            "publisher": ["reghub-publisher"],
            "editor": ["reghub-editor"],
            "viewer": ["reghub-viewer"],
        }
    )
    oidc_end_session_url: AnyHttpUrl | None = None

    github_token: SecretStr | None = None
    github_timeout_seconds: int = Field(default=15, ge=3, le=60)
    github_allow_private_repositories: bool = False

    gitlab_token: SecretStr | None = None
    bitbucket_username: str | None = None
    bitbucket_app_password: SecretStr | None = None
    provider_timeout_seconds: int = Field(default=20, ge=3, le=90)

    ai_metadata_enabled: bool = False
    ai_base_url: AnyHttpUrl | None = None
    ai_api_key: SecretStr | None = None
    ai_model: str = "gpt-4.1-mini"

    screenshot_service_url: AnyHttpUrl | None = None
    screenshot_service_token: SecretStr | None = None

    local_upload_enabled: bool = False
    local_upload_max_bytes: int = Field(default=25_000_000, ge=1024, le=100_000_000)
    local_upload_max_uncompressed_bytes: int = Field(default=100_000_000, ge=1024, le=500_000_000)
    local_upload_max_entries: int = Field(default=2000, ge=1, le=10000)

    public_api_cache_seconds: int = Field(default=60, ge=0, le=3600)

    redis_url: SecretStr | None = None
    operation_backend: Literal["inprocess", "redis"] = "inprocess"
    operation_queue_name: str = "reghub:operations"
    operation_worker_poll_seconds: float = Field(default=1.0, ge=0.1, le=30.0)
    operation_lock_ttl_seconds: int = Field(default=900, ge=60, le=86_400)
    cache_backend: Literal["disabled", "memory", "redis", "auto"] = "auto"
    catalog_cache_ttl_seconds: int = Field(default=60, ge=0, le=3600)
    rate_limit_enabled: bool = True
    rate_limit_backend: Literal["memory", "redis", "auto"] = "auto"
    rate_limit_public_per_minute: int = Field(default=180, ge=1, le=100_000)
    rate_limit_token_per_minute: int = Field(default=1200, ge=1, le=100_000)
    rate_limit_token_ip_per_minute: int = Field(default=2400, ge=1, le=100_000)
    rate_limit_admin_per_minute: int = Field(default=600, ge=1, le=100_000)
    trusted_proxy_networks: list[str] = Field(
        default_factory=lambda: [
            "127.0.0.1/32",
            "::1/128",
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16",
            "fc00::/7",
            "fe80::/10",
        ]
    )

    runtime_encryption_key: SecretStr | None = None
    runtime_encryption_previous_keys: list[SecretStr] = Field(default_factory=list)
    audit_signing_key: SecretStr | None = None
    audit_signing_previous_keys: list[SecretStr] = Field(default_factory=list)

    log_level: str = "INFO"

    @field_validator(
        "oidc_issuer_url",
        "oidc_client_id",
        "oidc_client_secret",
        "oidc_end_session_url",
        "github_token",
        "gitlab_token",
        "bitbucket_username",
        "bitbucket_app_password",
        "ai_base_url",
        "ai_api_key",
        "screenshot_service_url",
        "screenshot_service_token",
        "redis_url",
        "runtime_encryption_key",
        "audit_signing_key",
        mode="before",
    )
    @classmethod
    def blank_optional_values_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "allowed_hosts",
        "cors_origins",
        "oidc_admin_values",
        "trusted_proxy_networks",
        "runtime_encryption_previous_keys",
        "audit_signing_previous_keys",
        mode="before",
    )
    @classmethod
    def normalize_csv_or_list(cls, value: object) -> object:
        if isinstance(value, str) and not value.lstrip().startswith("["):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("allowed_hosts")
    @classmethod
    def validate_allowed_hosts(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(_normalize_allowed_host(item) for item in value))
        if not normalized:
            raise ValueError("ALLOWED_HOSTS must contain at least one host")
        return normalized

    @field_validator("trusted_proxy_networks")
    @classmethod
    def validate_trusted_proxy_networks(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            candidate = item.strip()
            if candidate == "*":
                normalized.append(candidate)
                continue
            try:
                normalized.append(str(ipaddress.ip_network(candidate, strict=False)))
            except ValueError as exc:
                raise ValueError(
                    f"TRUSTED_PROXY_NETWORKS contains an invalid IP/CIDR: {candidate}"
                ) from exc
        return list(dict.fromkeys(normalized))

    @field_validator("runtime_encryption_previous_keys", "audit_signing_previous_keys")
    @classmethod
    def normalize_previous_keys(cls, value: list[SecretStr]) -> list[SecretStr]:
        normalized: list[SecretStr] = []
        seen: set[str] = set()
        for item in value:
            candidate = item.get_secret_value().strip()
            if candidate and candidate not in seen:
                normalized.append(SecretStr(candidate))
                seen.add(candidate)
        return normalized

    @model_validator(mode="after")
    def validate_security_settings(self) -> Settings:
        if self.app_env != "production":
            return self

        session_secret = self.session_secret.get_secret_value().strip()
        runtime_key = _secret_value(self.runtime_encryption_key)
        audit_key = _secret_value(self.audit_signing_key)

        if session_secret in _INSECURE_EXAMPLE_SECRETS:
            raise ValueError("SESSION_SECRET must not use a development or example value")
        if len(session_secret) < 32:
            raise ValueError("SESSION_SECRET must contain at least 32 characters in production")
        if not runtime_key or runtime_key in _INSECURE_EXAMPLE_SECRETS:
            raise ValueError("RUNTIME_ENCRYPTION_KEY is required and must not use an example value")
        if len(runtime_key) < 32:
            raise ValueError("RUNTIME_ENCRYPTION_KEY must contain at least 32 characters")
        if not audit_key or audit_key in _INSECURE_EXAMPLE_SECRETS:
            raise ValueError("AUDIT_SIGNING_KEY is required and must not use an example value")
        if len(audit_key) < 32:
            raise ValueError("AUDIT_SIGNING_KEY must contain at least 32 characters")
        if len({session_secret, runtime_key, audit_key}) != 3:
            raise ValueError(
                "SESSION_SECRET, RUNTIME_ENCRYPTION_KEY and AUDIT_SIGNING_KEY must differ"
            )

        if not self.session_cookie_secure:
            raise ValueError("SESSION_COOKIE_SECURE must be true in production")
        if self.public_base_url.scheme != "https":
            raise ValueError("PUBLIC_BASE_URL must use HTTPS in production")
        if self.public_base_url.path not in {"", "/"}:
            raise ValueError("PUBLIC_BASE_URL must be an origin without a path")
        if self.public_base_url.query or self.public_base_url.fragment:
            raise ValueError("PUBLIC_BASE_URL must not contain a query or fragment")
        public_host = self.public_base_url.host
        if not public_host or not _host_is_allowed(public_host, self.allowed_hosts):
            raise ValueError("PUBLIC_BASE_URL host must be present in ALLOWED_HOSTS")
        if "*" in self.allowed_hosts:
            raise ValueError("ALLOWED_HOSTS must not contain wildcard '*' in production")
        if "*" in self.trusted_proxy_networks:
            raise ValueError("TRUSTED_PROXY_NETWORKS must not contain wildcard in production")
        for origin in self.cors_origins:
            parsed_origin = urlsplit(origin)
            if (
                parsed_origin.scheme != "https"
                or not parsed_origin.hostname
                or parsed_origin.username
                or parsed_origin.password
                or parsed_origin.path not in {"", "/"}
                or parsed_origin.query
                or parsed_origin.fragment
            ):
                raise ValueError("CORS_ORIGINS must contain HTTPS origins only in production")

        parsed_database = urlsplit(self.database_url)
        if parsed_database.scheme != "postgresql+asyncpg" or not parsed_database.hostname:
            raise ValueError("DATABASE_URL must use postgresql+asyncpg in production")

        required = [self.oidc_issuer_url, self.oidc_client_id, self.oidc_client_secret]
        if not all(required):
            raise ValueError("OIDC issuer, client ID, and client secret are required in production")
        secure_urls = (
            ("OIDC_ISSUER_URL", self.oidc_issuer_url),
            ("OIDC_END_SESSION_URL", self.oidc_end_session_url),
            ("AI_BASE_URL", self.ai_base_url),
            ("SCREENSHOT_SERVICE_URL", self.screenshot_service_url),
        )
        for field_name, value in secure_urls:
            if value is None:
                continue
            if value.scheme != "https":
                raise ValueError(f"{field_name} must use HTTPS in production")
            parsed_value = urlsplit(str(value))
            if parsed_value.username or parsed_value.password:
                raise ValueError(f"{field_name} must not contain embedded credentials")
            if parsed_value.fragment:
                raise ValueError(f"{field_name} must not contain a URL fragment")

        if not self.oidc_admin_values and not any(self.oidc_role_values.values()):
            raise ValueError("OIDC administrator role values cannot be empty in production")
        if self.github_allow_private_repositories and not self.github_token:
            raise ValueError("GITHUB_TOKEN is required for private GitHub repositories")
        if self.ai_metadata_enabled and not (self.ai_base_url and self.ai_api_key):
            raise ValueError("AI_BASE_URL and AI_API_KEY are required when AI metadata is enabled")
        if self.screenshot_service_token and not self.screenshot_service_url:
            raise ValueError("SCREENSHOT_SERVICE_URL is required when its token is configured")
        if bool(self.bitbucket_username) != bool(self.bitbucket_app_password):
            raise ValueError(
                "BITBUCKET_USERNAME and BITBUCKET_APP_PASSWORD must be configured together"
            )
        if self.operation_backend == "redis" and not self.redis_url:
            raise ValueError("REDIS_URL is required when OPERATION_BACKEND=redis")
        if self.cache_backend == "redis" and not self.redis_url:
            raise ValueError("REDIS_URL is required when CACHE_BACKEND=redis")
        if self.rate_limit_backend == "redis" and not self.redis_url:
            raise ValueError("REDIS_URL is required when RATE_LIMIT_BACKEND=redis")
        return self

    @property
    def oidc_enabled(self) -> bool:
        return bool(self.oidc_issuer_url and self.oidc_client_id and self.oidc_client_secret)

    @property
    def base_url(self) -> str:
        return str(self.public_base_url).rstrip("/")

    @property
    def redis_dsn(self) -> str | None:
        return self.redis_url.get_secret_value() if self.redis_url else None

    @property
    def runtime_keyring(self) -> list[str]:
        keys: list[str] = []
        if self.runtime_encryption_key:
            keys.append(self.runtime_encryption_key.get_secret_value())
        keys.extend(item.get_secret_value() for item in self.runtime_encryption_previous_keys)
        keys.append(self.session_secret.get_secret_value())
        return list(dict.fromkeys(keys))

    @property
    def effective_audit_signing_key(self) -> str:
        if self.audit_signing_key:
            return self.audit_signing_key.get_secret_value()
        if self.runtime_encryption_key:
            return self.runtime_encryption_key.get_secret_value()
        return self.session_secret.get_secret_value()

    @property
    def audit_keyring(self) -> list[str]:
        keys = [self.effective_audit_signing_key]
        keys.extend(item.get_secret_value() for item in self.audit_signing_previous_keys)
        keys.extend(self.runtime_keyring)
        return list(dict.fromkeys(keys))


@lru_cache
def get_settings() -> Settings:
    return Settings()
