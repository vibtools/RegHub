from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analyzer.framework import detect_framework
from app.models.framework import Framework
from app.registry.adapters.base import ImportedRepository


class FrameworkService:
    @staticmethod
    async def list_active(session: AsyncSession) -> list[Framework]:
        return list(
            (
                await session.scalars(
                    select(Framework).where(Framework.is_active.is_(True)).order_by(Framework.name)
                )
            ).all()
        )

    @staticmethod
    def detect_slug(repository: ImportedRepository) -> str:
        """Backward-compatible detection entrypoint used by existing integrations/tests."""
        return detect_framework(repository).slug

    @staticmethod
    async def resolve(session: AsyncSession, slug: str) -> Framework:
        framework = await session.scalar(
            select(Framework).where(Framework.slug == slug, Framework.is_active.is_(True))
        )
        if framework is None and slug != "unknown":
            framework = await session.scalar(select(Framework).where(Framework.slug == "unknown"))
        if framework is None:
            raise RuntimeError("The required 'unknown' framework seed is missing")
        return framework
