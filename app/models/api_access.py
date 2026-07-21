from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import JSON_VARIANT
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ApiAccessPolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "api_access_policies"

    key: Mapped[str] = mapped_column(String(80), unique=True, index=True, default="default")
    mode: Mapped[str] = mapped_column(String(24), default="development", index=True)
    updated_by: Mapped[str | None] = mapped_column(String(255))


class ApiServiceToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "api_service_tokens"

    name: Mapped[str] = mapped_column(String(160), index=True)
    token_prefix: Mapped[str] = mapped_column(String(32), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    last_four: Mapped[str] = mapped_column(String(8))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    scopes: Mapped[list[str]] = mapped_column(JSON_VARIANT, default=list)
    description: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(String(255))
    updated_by: Mapped[str | None] = mapped_column(String(255))

    def __str__(self) -> str:
        return f"{self.name} ({self.token_prefix}…{self.last_four})"


class ApiBlockRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "api_block_rules"

    value: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    rule_type: Mapped[str] = mapped_column(String(24), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    note: Mapped[str | None] = mapped_column(String(500))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON_VARIANT, default=dict)
    created_by: Mapped[str | None] = mapped_column(String(255))
    updated_by: Mapped[str | None] = mapped_column(String(255))

    def __str__(self) -> str:
        return self.value
