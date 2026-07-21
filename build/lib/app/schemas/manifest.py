from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import DeployType


class DeployManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: DeployType = DeployType.UNKNOWN


class BuildManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str | None = Field(default=None, max_length=500)
    start_command: str | None = Field(default=None, max_length=500)


class EnvironmentManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=128)
    required: bool = False
    secret: bool = False
    description: str | None = Field(default=None, max_length=300)


class TemplateManifest(BaseModel):
    """Versioned deployment-neutral template manifest.

    v1 fields remain accepted. v2 adds metadata used by the YGIT deployment engine.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="2.0", pattern=r"^(?:1\.0|2\.0)$")
    name: str | None = Field(default=None, min_length=1, max_length=160)
    framework: str = Field(min_length=1, max_length=120)
    framework_version: str | None = Field(default=None, max_length=80)
    language: str | None = Field(default=None, max_length=100)
    package_manager: str | None = Field(default=None, max_length=40)
    repository: str = Field(min_length=1, max_length=500)
    branch: str = Field(min_length=1, max_length=255)
    build: BuildManifest | None = None
    deploy: DeployManifest
    environment: list[EnvironmentManifest] = Field(default_factory=list, max_length=50)

    @field_validator("repository")
    @classmethod
    def validate_repository(cls, value: str) -> str:
        if value.startswith("local://"):
            return value
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("repository must use HTTPS or local://")
        if parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment:
            raise ValueError("repository URL cannot include credentials, ports, query, or fragment")
        if parsed.hostname.casefold() not in {
            "github.com",
            "www.github.com",
            "gitlab.com",
            "www.gitlab.com",
            "bitbucket.org",
            "www.bitbucket.org",
        }:
            raise ValueError("repository host is not supported")
        return value.rstrip("/").removesuffix(".git")

    @model_validator(mode="after")
    def validate_version_shape(self) -> "TemplateManifest":
        if self.schema_version == "2.0" and not self.name:
            raise ValueError("manifest v2 requires name")
        return self

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)
