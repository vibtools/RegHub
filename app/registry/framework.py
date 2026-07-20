from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.framework import Framework
from app.registry.adapters.base import ImportedRepository

_FRAMEWORK_TOPIC_MAP = {
    "astro": "astro",
    "nextjs": "nextjs",
    "next-js": "nextjs",
    "react": "react",
    "vue": "vue",
    "nuxt": "nuxt",
    "sveltekit": "sveltekit",
    "svelte-kit": "sveltekit",
    "laravel": "laravel",
    "django": "django",
    "fastapi": "fastapi",
}

_FILE_MAP = {
    "astro.config.mjs": "astro",
    "astro.config.ts": "astro",
    "astro.config.js": "astro",
    "astro.config.cjs": "astro",
    "next.config.js": "nextjs",
    "next.config.mjs": "nextjs",
    "next.config.ts": "nextjs",
    "nuxt.config.ts": "nuxt",
    "nuxt.config.js": "nuxt",
    "svelte.config.js": "sveltekit",
    "svelte.config.ts": "sveltekit",
    "artisan": "laravel",
    "manage.py": "django",
    "dockerfile": "docker",
}

_PACKAGE_MAP = {
    "astro": "astro",
    "next": "nextjs",
    "nuxt": "nuxt",
    "@sveltejs/kit": "sveltekit",
    "vue": "vue",
    "react": "react",
}


def _package_names(package_json: dict[str, Any] | None) -> set[str]:
    if not isinstance(package_json, dict):
        return set()
    names: set[str] = set()
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        values = package_json.get(section)
        if isinstance(values, dict):
            names.update(str(name).casefold() for name in values)
    return names


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
        # Explicit GitHub topics have highest priority because they are maintainer supplied.
        for topic in repository.topics:
            if topic in _FRAMEWORK_TOPIC_MAP:
                return _FRAMEWORK_TOPIC_MAP[topic]

        # package.json allows Astro/Next.js/etc. imports even when the config file has
        # a non-standard name or is absent from the root. Astro is checked before React
        # because Astro projects may also include React integrations.
        packages = _package_names(repository.package_json)
        for package_name, framework in _PACKAGE_MAP.items():
            if package_name in packages:
                return framework

        for filename, framework in _FILE_MAP.items():
            if filename in repository.root_files:
                return framework
        if "index.html" in repository.root_files:
            return "static-html"
        return "unknown"

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
