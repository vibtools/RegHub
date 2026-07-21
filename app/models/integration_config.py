from typing import Any

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import JSON_VARIANT
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class IntegrationConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "integration_configs"

    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    integration_type: Mapped[str] = mapped_column(String(80), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    base_url: Mapped[str | None] = mapped_column(String(1000))
    username: Mapped[str | None] = mapped_column(String(255))
    secret_encrypted: Mapped[str | None] = mapped_column(Text)
    use_environment_fallback: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON_VARIANT, default=dict)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    updated_by: Mapped[str | None] = mapped_column(String(255))

    def __str__(self) -> str:
        return self.name
