from datetime import datetime
from typing import Any
from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import JSON_VARIANT
from app.models.mixins import UUIDPrimaryKeyMixin


class AuditChainState(Base):
    __tablename__ = "audit_chain_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_sequence: Mapped[int] = mapped_column(BigInteger, default=0)
    last_hash: Mapped[str] = mapped_column(String(128), default="GENESIS")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"

    sequence: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    actor_subject: Mapped[str | None] = mapped_column(String(255), index=True)
    actor_email: Mapped[str | None] = mapped_column(String(320))
    actor_roles: Mapped[list[str]] = mapped_column(JSON_VARIANT, default=list)
    action: Mapped[str] = mapped_column(String(160), index=True)
    resource_type: Mapped[str] = mapped_column(String(120), index=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), index=True)
    outcome: Mapped[str] = mapped_column(String(32), default="succeeded", index=True)
    request_id: Mapped[str | None] = mapped_column(String(100), index=True)
    client_ip: Mapped[str | None] = mapped_column(String(80))
    details: Mapped[dict[str, Any]] = mapped_column(JSON_VARIANT, default=dict)
    signing_key_id: Mapped[str] = mapped_column(String(12), index=True)
    previous_hash: Mapped[str] = mapped_column(String(128))
    event_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)

    def __str__(self) -> str:
        return f"#{self.sequence} {self.action}"
