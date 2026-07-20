import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.enums import ProviderType
from app.database.session import async_session_factory
from app.models.category import Category
from app.models.framework import Framework
from app.models.provider import Provider

FRAMEWORKS = [
    ("Unknown", "unknown", None),
    ("Astro", "astro", "https://astro.build"),
    ("Next.js", "nextjs", "https://nextjs.org"),
    ("React", "react", "https://react.dev"),
    ("Vue", "vue", "https://vuejs.org"),
    ("Nuxt", "nuxt", "https://nuxt.com"),
    ("SvelteKit", "sveltekit", "https://svelte.dev"),
    ("Laravel", "laravel", "https://laravel.com"),
    ("Django", "django", "https://www.djangoproject.com"),
    ("FastAPI", "fastapi", "https://fastapi.tiangolo.com"),
    ("Static HTML", "static-html", None),
    ("Docker", "docker", "https://www.docker.com"),
]


async def seed() -> None:
    async with async_session_factory() as session:
        for name, slug, website in FRAMEWORKS:
            exists = await session.scalar(select(Framework.id).where(Framework.slug == slug))
            if not exists:
                session.add(Framework(name=name, slug=slug, website_url=website, is_active=True))
        if not await session.scalar(select(Provider.id).where(Provider.slug == "official")):
            session.add(
                Provider(
                    name="YGIT Official",
                    slug="official",
                    provider_type=ProviderType.OFFICIAL,
                    website_url="https://ygit.net",
                    is_active=True,
                )
            )
        if not await session.scalar(select(Category.id).where(Category.slug == "general")):
            session.add(Category(name="General", slug="general", is_active=True))
        await session.commit()
        print(f"RegHub seed complete at {datetime.now(UTC).isoformat()}")


if __name__ == "__main__":
    asyncio.run(seed())
