from enum import StrEnum


class TemplateStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DISABLED = "disabled"


class ProviderType(StrEnum):
    OFFICIAL = "official"
    COMMUNITY = "community"
    PARTNER = "partner"
    ORGANIZATION = "organization"
    INDIVIDUAL = "individual"


class ImportStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class DeployType(StrEnum):
    STATIC = "static"
    NODE = "node"
    PYTHON = "python"
    PHP = "php"
    DOCKER = "docker"
    UNKNOWN = "unknown"


class ScreenshotJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
