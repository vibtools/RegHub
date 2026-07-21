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
    ("React + Vite", "react-vite", "https://vite.dev"),
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

CATEGORIES = [
    ("General", "general", "General-purpose templates and starters"),
    ("SaaS", "saas", "SaaS products, dashboards, and admin applications"),
    ("E-commerce", "ecommerce", "Online stores and commerce experiences"),
    ("Portfolio", "portfolio", "Personal and agency portfolio sites"),
    ("Content", "content", "Blogs, documentation, CMS, and content sites"),
    ("Landing Pages", "landing-pages", "Marketing and campaign landing pages"),
]


async def seed() -> None:
    async with async_session_factory() as session:
        for name, slug, website in FRAMEWORKS:
            exists = await session.scalar(select(Framework.id).where(Framework.slug == slug))
            if not exists:
                session.add(Framework(name=name, slug=slug, website_url=website, is_active=True))
        providers = [
            ("YGIT Official", "official", ProviderType.OFFICIAL, "https://ygit.net"),
            ("Community", "community", ProviderType.COMMUNITY, None),
        ]
        for name, slug, provider_type, website in providers:
            if not await session.scalar(select(Provider.id).where(Provider.slug == slug)):
                session.add(
                    Provider(
                        name=name,
                        slug=slug,
                        provider_type=provider_type,
                        website_url=website,
                        is_active=True,
                    )
                )
        for name, slug, description in CATEGORIES:
            if not await session.scalar(select(Category.id).where(Category.slug == slug)):
                session.add(
                    Category(
                        name=name,
                        slug=slug,
                        description=description,
                        is_active=True,
                    )
                )
        await session.commit()
        print(f"RegHub seed complete at {datetime.now(UTC).isoformat()}")


if __name__ == "__main__":
    asyncio.run(seed())
