from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import DeployType


class DeployManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: DeployType = DeployType.UNKNOWN


class TemplateManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="1.0", pattern=r"^1\.0$")
    framework: str = Field(min_length=1, max_length=120)
    repository: str = Field(pattern=r"^https://github\.com/[^/]+/[^/]+$")
    branch: str = Field(min_length=1, max_length=255)
    deploy: DeployManifest
