from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class TemplateAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "template_assets"
    __table_args__ = (
        UniqueConstraint(
            "template_id",
            "kind",
            "url",
            "source",
            name="uq_template_assets_identity",
        ),
        CheckConstraint(
            "sort_order >= 0",
            name="ck_template_assets_sort_order_nonnegative",
        ),
    )

    template_id: Mapped[UUID] = mapped_column(
        ForeignKey("templates.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40), index=True)
    url: Mapped[str] = mapped_column(String(1000))
    source: Mapped[str] = mapped_column(String(40), default="repository")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    template = relationship("Template", back_populates="assets", lazy="joined")
