from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category


class CategoryService:
    @staticmethod
    async def list_active(session: AsyncSession) -> list[Category]:
        return list(
            (
                await session.scalars(
                    select(Category).where(Category.is_active.is_(True)).order_by(Category.name)
                )
            ).all()
        )
