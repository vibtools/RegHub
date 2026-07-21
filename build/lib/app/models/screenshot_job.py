from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ScreenshotJobStatus
from app.database.base import Base
from app.database.types import JSON_VARIANT
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ScreenshotJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "screenshot_jobs"

    template_id: Mapped[UUID] = mapped_column(
        ForeignKey("templates.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[ScreenshotJobStatus] = mapped_column(
        Enum(ScreenshotJobStatus, native_enum=False, length=32),
        default=ScreenshotJobStatus.PENDING,
        index=True,
    )
    preview_url: Mapped[str] = mapped_column(String(1000))
    screenshot_url: Mapped[str | None] = mapped_column(String(1000))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    requested_by: Mapped[str | None] = mapped_column(String(255), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    response_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON_VARIANT)
    completed_at: Mapped[datetime | None]

    template = relationship("Template", back_populates="screenshot_jobs", lazy="joined")
