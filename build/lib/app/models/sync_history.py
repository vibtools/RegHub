from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ImportStatus
from app.database.base import Base
from app.database.types import JSON_VARIANT
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class SyncHistory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sync_history"

    template_id: Mapped[UUID] = mapped_column(
        ForeignKey("templates.id", ondelete="CASCADE"), index=True
    )
    adapter: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[ImportStatus] = mapped_column(
        Enum(ImportStatus, native_enum=False, length=32), default=ImportStatus.PENDING, index=True
    )
    trigger: Mapped[str] = mapped_column(String(40), default="manual", index=True)
    requested_by: Mapped[str | None] = mapped_column(String(255), index=True)
    source_revision: Mapped[str | None] = mapped_column(String(160))
    metadata_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON_VARIANT)
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSON_VARIANT)
    error_message: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None]

    template = relationship("Template", back_populates="sync_history", lazy="joined")
