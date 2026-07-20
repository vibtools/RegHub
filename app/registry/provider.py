from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provider import Provider


class ProviderService:
    @staticmethod
    async def list_active(session: AsyncSession) -> list[Provider]:
        return list(
            (
                await session.scalars(
                    select(Provider).where(Provider.is_active.is_(True)).order_by(Provider.name)
                )
            ).all()
        )
