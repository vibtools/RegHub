import ipaddress
from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    session_secret: SecretStr = SecretStr("development-secret-change-this-value")
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

    # v0.3.0 infrastructure settings. Defaults preserve the v0.2.3.4 deployment.
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

    # First key encrypts new values. Previous keys decrypt values during rotation.
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

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        if self.app_env == "production":
            if len(self.session_secret.get_secret_value()) < 32:
                raise ValueError("SESSION_SECRET must contain at least 32 characters in production")
            if not self.session_cookie_secure:
                raise ValueError("SESSION_COOKIE_SECURE must be true in production")
            required = [self.oidc_issuer_url, self.oidc_client_id, self.oidc_client_secret]
            if not all(required):
                raise ValueError(
                    "OIDC issuer, client ID, and client secret are required in production"
                )
            if not self.oidc_admin_values and not any(self.oidc_role_values.values()):
                raise ValueError("OIDC administrator role values cannot be empty in production")
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
        keys.extend(
            item.get_secret_value() for item in self.runtime_encryption_previous_keys if item
        )
        # Legacy fallback keeps all existing v0.2.x encrypted credentials readable.
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
        keys.extend(item.get_secret_value() for item in self.audit_signing_previous_keys if item)
        # When the dedicated audit key is not configured, audit signing follows the
        # versioned runtime keyring so runtime-key rotation remains verifiable.
        keys.extend(self.runtime_keyring)
        return list(dict.fromkeys(keys))


@lru_cache
def get_settings() -> Settings:
    return Settings()
