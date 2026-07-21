from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.manifest import TemplateManifest


class NamedResource(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str


class CategoryRead(NamedResource):
    description: str | None


class ProviderRead(NamedResource):
    provider_type: str
    website_url: str | None


class FrameworkRead(NamedResource):
    description: str | None
    website_url: str | None
    icon_url: str | None


class TemplateListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    short_description: str | None
    repository_url: str
    repository_adapter: str
    default_branch: str
    preview_url: str | None
    thumbnail_url: str | None
    screenshots: list[str]
    license_spdx: str | None
    primary_language: str | None
    framework_version: str | None
    package_manager: str | None
    difficulty: str | None
    use_case: str | None
    topics: list[str]
    quality_score: int
    stars_count: int
    forks_count: int
    is_featured: bool
    category: NamedResource | None
    provider: NamedResource | None
    framework: NamedResource | None
    published_at: datetime | None
    updated_at: datetime


class TemplateDetail(TemplateListItem):
    description: str | None
    homepage_url: str | None
    quality_breakdown: dict[str, int]
    analysis: dict[str, Any]
    manifest: TemplateManifest


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int


class ResponseMeta(BaseModel):
    api_version: str = "v1"
    request_id: str


class TemplatePage(BaseModel):
    data: list[TemplateListItem]
    pagination: PaginationMeta
    meta: ResponseMeta


class CapabilitiesRead(BaseModel):
    version: str
    registry_adapters: list[str]
    framework_detection: list[str]
    manifest_versions: list[str]
    local_upload_enabled: bool
    ai_metadata_enabled: bool
    screenshot_service_enabled: bool
