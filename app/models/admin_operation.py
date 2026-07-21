from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import OperationStatus
from app.database.base import Base
from app.database.types import JSON_VARIANT
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AdminOperation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "admin_operations"

    operation_type: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(240))
    status: Mapped[OperationStatus] = mapped_column(
        Enum(OperationStatus, native_enum=False, length=32),
        default=OperationStatus.QUEUED,
        index=True,
    )
    progress: Mapped[int] = mapped_column(Integer, default=0)
    requested_by: Mapped[str | None] = mapped_column(String(255), index=True)
    return_url: Mapped[str | None] = mapped_column(String(1000))
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON_VARIANT, default=dict)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON_VARIANT)
    error_message: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    retry_of_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("admin_operations.id", ondelete="SET NULL"), index=True
    )
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]

    logs = relationship(
        "OperationLog",
        back_populates="operation",
        cascade="all, delete-orphan",
        order_by="OperationLog.sequence",
    )

    def __str__(self) -> str:
        return f"{self.title} ({self.status.value})"


class OperationLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "operation_logs"
    __table_args__ = (UniqueConstraint("operation_id", "sequence"),)

    operation_id: Mapped[UUID] = mapped_column(
        ForeignKey("admin_operations.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    level: Mapped[str] = mapped_column(String(20), default="info", index=True)
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSON_VARIANT)
    created_at: Mapped[datetime]

    operation = relationship("AdminOperation", back_populates="logs")
