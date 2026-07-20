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
    oidc_end_session_url: AnyHttpUrl | None = None

    github_token: SecretStr | None = None
    github_timeout_seconds: int = Field(default=15, ge=3, le=60)
    github_allow_private_repositories: bool = False

    public_api_cache_seconds: int = Field(default=60, ge=0, le=3600)
    log_level: str = "INFO"

    @field_validator(
        "oidc_issuer_url",
        "oidc_client_id",
        "oidc_client_secret",
        "oidc_end_session_url",
        "github_token",
        mode="before",
    )
    @classmethod
    def blank_optional_values_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("allowed_hosts", "cors_origins", "oidc_admin_values", mode="before")
    @classmethod
    def normalize_csv_or_list(cls, value: object) -> object:
        if isinstance(value, str) and not value.lstrip().startswith("["):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        if self.app_env == "production":
            if len(self.session_secret.get_secret_value()) < 32:
                raise ValueError("SESSION_SECRET must contain at least 32 characters in production")
            if not self.session_cookie_secure:
                raise ValueError("SESSION_COOKIE_SECURE must be true in production")
            required = [self.oidc_issuer_url, self.oidc_client_id, self.oidc_client_secret]
            if not all(required):
                raise ValueError("OIDC issuer, client ID, and client secret are required in production")
            if not self.oidc_admin_values:
                raise ValueError("OIDC_ADMIN_VALUES cannot be empty in production")
        return self

    @property
    def oidc_enabled(self) -> bool:
        return bool(self.oidc_issuer_url and self.oidc_client_id and self.oidc_client_secret)

    @property
    def base_url(self) -> str:
        return str(self.public_base_url).rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
