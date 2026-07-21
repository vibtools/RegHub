from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class TemplateAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "template_assets"

    template_id: Mapped[UUID] = mapped_column(
        ForeignKey("templates.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40), index=True)
    url: Mapped[str] = mapped_column(String(1000))
    source: Mapped[str] = mapped_column(String(40), default="repository")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    template = relationship("Template", back_populates="assets", lazy="joined")
