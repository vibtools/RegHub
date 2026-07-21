from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import TemplateStatus
from app.database.base import Base
from app.database.types import JSON_VARIANT
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Template(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "templates"
    __table_args__ = (Index("ix_templates_public_catalog", "status", "is_featured", "created_at"),)

    name: Mapped[str] = mapped_column(String(160), index=True)
    slug: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    short_description: Mapped[str | None] = mapped_column(String(320))
    description: Mapped[str | None] = mapped_column(Text)

    repository_url: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    repository_adapter: Mapped[str] = mapped_column(String(50), default="github", index=True)
    external_repository_id: Mapped[str | None] = mapped_column(String(160), unique=True)
    default_branch: Mapped[str] = mapped_column(String(255), default="main")
    homepage_url: Mapped[str | None] = mapped_column(String(500))
    preview_url: Mapped[str | None] = mapped_column(String(500))
    thumbnail_url: Mapped[str | None] = mapped_column(String(500))
    screenshots: Mapped[list[str]] = mapped_column(JSON_VARIANT, default=list)
    license_spdx: Mapped[str | None] = mapped_column(String(100))
    primary_language: Mapped[str | None] = mapped_column(String(100), index=True)
    framework_version: Mapped[str | None] = mapped_column(String(80))
    package_manager: Mapped[str | None] = mapped_column(String(40))
    difficulty: Mapped[str | None] = mapped_column(String(32), index=True)
    use_case: Mapped[str | None] = mapped_column(String(160), index=True)
    topics: Mapped[list[str]] = mapped_column(JSON_VARIANT, default=list)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON_VARIANT, default=dict)
    analysis: Mapped[dict[str, Any]] = mapped_column(JSON_VARIANT, default=dict)
    quality_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    quality_breakdown: Mapped[dict[str, int]] = mapped_column(JSON_VARIANT, default=dict)
    stars_count: Mapped[int] = mapped_column(Integer, default=0)
    forks_count: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[TemplateStatus] = mapped_column(
        Enum(TemplateStatus, native_enum=False, length=32),
        default=TemplateStatus.DRAFT,
        index=True,
    )
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    published_at: Mapped[datetime | None]
    last_synced_at: Mapped[datetime | None]
    source_updated_at: Mapped[datetime | None]
    last_analysis_at: Mapped[datetime | None]
    created_by: Mapped[str | None] = mapped_column(String(255))

    category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    provider_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("providers.id", ondelete="SET NULL"), index=True
    )
    framework_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("frameworks.id", ondelete="SET NULL"), index=True
    )

    category = relationship("Category", back_populates="templates", lazy="joined")
    provider = relationship("Provider", back_populates="templates", lazy="joined")
    framework = relationship("Framework", back_populates="templates", lazy="joined")
    versions = relationship(
        "TemplateVersion", back_populates="template", cascade="all, delete-orphan"
    )
    sync_history = relationship(
        "SyncHistory", back_populates="template", cascade="all, delete-orphan"
    )
    assets = relationship("TemplateAsset", back_populates="template", cascade="all, delete-orphan")

    def __str__(self) -> str:
        return self.name
