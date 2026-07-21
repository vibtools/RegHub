from slugify import slugify
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ProviderType
from app.models.provider import Provider
from app.registry.adapters.base import ImportedRepository

_OFFICIAL_OWNERS = {"vibtools", "ygit"}


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

    @staticmethod
    def _provider_type(imported: ImportedRepository) -> ProviderType:
        owner_type = (imported.owner_type or "").casefold()
        if owner_type in {"organization", "group", "workspace", "team"}:
            return ProviderType.ORGANIZATION
        if owner_type in {"user", "individual"}:
            return ProviderType.INDIVIDUAL
        return ProviderType.COMMUNITY

    @staticmethod
    async def _safe_name(session: AsyncSession, *, desired: str, slug: str, adapter: str) -> str:
        desired = desired.strip()[:120] or slug
        collision = await session.scalar(
            select(Provider).where(
                func.lower(Provider.name) == desired.casefold(), Provider.slug != slug
            )
        )
        if collision is None:
            return desired
        owner_suffix = slug.rsplit("-", 1)[-1][:28]
        suffix = f" ({adapter.title()}:{owner_suffix})"
        return f"{desired[: 120 - len(suffix)]}{suffix}"

    @classmethod
    async def resolve_for_repository(
        cls,
        session: AsyncSession,
        imported: ImportedRepository,
    ) -> Provider | None:
        owner_login = (imported.owner_login or "").strip()
        if not owner_login:
            return await session.scalar(
                select(Provider).where(Provider.slug == "community", Provider.is_active.is_(True))
            )

        if owner_login.casefold() in _OFFICIAL_OWNERS:
            official = await session.scalar(
                select(Provider).where(Provider.slug == "official", Provider.is_active.is_(True))
            )
            if official:
                return official

        slug = f"{imported.adapter}-{slugify(owner_login)[:110]}"[:140]
        provider = await session.scalar(
            select(Provider).where(func.lower(Provider.slug) == slug.casefold())
        )
        desired_name = await cls._safe_name(
            session,
            desired=(imported.owner_name or owner_login),
            slug=slug,
            adapter=imported.adapter,
        )
        desired_url = imported.owner_url or None
        desired_type = cls._provider_type(imported)
        if provider:
            provider.name = desired_name
            if desired_url:
                provider.website_url = desired_url[:500]
            provider.provider_type = desired_type
            provider.is_active = True
            await session.flush()
            return provider

        provider = Provider(
            name=desired_name,
            slug=slug,
            provider_type=desired_type,
            website_url=(desired_url[:500] if desired_url else None),
            is_active=True,
        )
        # A nested transaction keeps the outer import transaction valid on a rare concurrent create.
        try:
            async with session.begin_nested():
                session.add(provider)
                await session.flush()
            return provider
        except IntegrityError:
            return await session.scalar(
                select(Provider).where(func.lower(Provider.slug) == slug.casefold())
            )
