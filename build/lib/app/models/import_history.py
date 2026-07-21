from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ImportStatus
from app.database.base import Base
from app.database.types import JSON_VARIANT
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ImportHistory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "import_history"

    adapter: Mapped[str] = mapped_column(String(50), default="github", index=True)
    repository_url: Mapped[str] = mapped_column(String(500), index=True)
    status: Mapped[ImportStatus] = mapped_column(
        Enum(ImportStatus, native_enum=False, length=32),
        default=ImportStatus.PENDING,
        index=True,
    )
    requested_by: Mapped[str | None] = mapped_column(String(255))
    metadata_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON_VARIANT)
    error_message: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None]
    template_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("templates.id", ondelete="SET NULL"), index=True
    )

    template = relationship("Template")

    def __str__(self) -> str:
        return f"{self.repository_url} ({self.status})"
