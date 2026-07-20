from datetime import datetime
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
    default_branch: str
    thumbnail_url: str | None
    license_spdx: str | None
    primary_language: str | None
    topics: list[str]
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
