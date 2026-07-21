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
    provider_auto_create_enabled: bool = False
    media_gallery_enabled: bool = False
    freshness_api_enabled: bool = False
    operations_console_enabled: bool = False
    public_api_enabled: bool = True
    api_access_mode: str = "development"
    service_token_required: bool = False


class TemplateAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    url: str
    source: str
    sort_order: int
    created_at: datetime
    updated_at: datetime


class FreshnessRead(BaseModel):
    template_id: UUID
    slug: str
    updated_at: datetime
    source_updated_at: datetime | None
    last_synced_at: datetime | None
    last_analysis_at: datetime | None
    source_revision: str | None
    sync_status: str | None
    is_stale: bool


class FacetItem(BaseModel):
    name: str
    slug: str
    count: int


class CatalogFacets(BaseModel):
    categories: list[FacetItem]
    providers: list[FacetItem]
    frameworks: list[FacetItem]
    languages: list[FacetItem]
    difficulties: list[FacetItem]


class AssetListResponse(BaseModel):
    data: list[TemplateAssetRead]
    meta: ResponseMeta


class FreshnessResponse(BaseModel):
    data: FreshnessRead
    meta: ResponseMeta


class FacetsResponse(BaseModel):
    data: CatalogFacets
    meta: ResponseMeta
