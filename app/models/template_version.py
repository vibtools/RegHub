from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.types import JSON_VARIANT
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class TemplateVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "template_versions"

    template_id: Mapped[UUID] = mapped_column(
        ForeignKey("templates.id", ondelete="CASCADE"), index=True
    )
    source_revision: Mapped[str | None] = mapped_column(String(160), index=True)
    metadata_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON_VARIANT, default=dict)
    manifest_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON_VARIANT, default=dict)
    analysis_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON_VARIANT, default=dict)

    template = relationship("Template", back_populates="versions", lazy="joined")
