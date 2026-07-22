from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ProviderType
from app.database.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Provider(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "providers"

    name: Mapped[str] = mapped_column(String(120), unique=True)
    slug: Mapped[str] = mapped_column(String(140), unique=True)
    provider_type: Mapped[ProviderType] = mapped_column(
        Enum(ProviderType, native_enum=False, length=32), default=ProviderType.COMMUNITY
    )
    website_url: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    templates = relationship("Template", back_populates="provider")

    def __str__(self) -> str:
        return self.name
