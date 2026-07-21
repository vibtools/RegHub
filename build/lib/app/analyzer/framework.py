from dataclasses import dataclass

from app.analyzer.package import package_names, package_version
from app.registry.adapters.base import ImportedRepository


@dataclass(frozen=True, slots=True)
class FrameworkDetection:
    slug: str
    name: str
    version: str | None
    confidence: int
    evidence: list[str]


_FRAMEWORK_NAMES = {
    "unknown": "Unknown",
    "astro": "Astro",
    "nextjs": "Next.js",
    "react-vite": "React + Vite",
    "react": "React",
    "vue": "Vue",
    "nuxt": "Nuxt",
    "sveltekit": "SvelteKit",
    "laravel": "Laravel",
    "django": "Django",
    "fastapi": "FastAPI",
    "static-html": "Static HTML",
    "docker": "Docker",
}


def _result(slug: str, version: str | None, confidence: int, *evidence: str) -> FrameworkDetection:
    return FrameworkDetection(slug, _FRAMEWORK_NAMES[slug], version, confidence, list(evidence))


def detect_framework(repository: ImportedRepository) -> FrameworkDetection:
    topics = {topic.casefold() for topic in repository.topics}
    files = {name.casefold() for name in repository.root_files}
    packages = package_names(repository.package_json)
    package_json = repository.package_json

    # Framework-specific package/config evidence outranks generic React/Vue dependencies.
    if (
        "astro" in packages
        or any(name.startswith("astro.config.") for name in files)
        or "astro" in topics
    ):
        return _result(
            "astro", package_version(package_json, "astro"), 100, "Astro package/config/topic"
        )
    if (
        "next" in packages
        or any(name.startswith("next.config.") for name in files)
        or {"nextjs", "next-js"} & topics
    ):
        return _result(
            "nextjs", package_version(package_json, "next"), 100, "Next.js package/config/topic"
        )
    if (
        "nuxt" in packages
        or any(name.startswith("nuxt.config.") for name in files)
        or "nuxt" in topics
    ):
        return _result(
            "nuxt", package_version(package_json, "nuxt"), 100, "Nuxt package/config/topic"
        )
    if (
        "@sveltejs/kit" in packages
        or "svelte.config.js" in files
        or "svelte.config.ts" in files
        or "sveltekit" in topics
    ):
        return _result(
            "sveltekit",
            package_version(package_json, "@sveltejs/kit"),
            100,
            "SvelteKit package/config/topic",
        )

    has_vite = "vite" in packages or any(name.startswith("vite.config.") for name in files)
    if "react" in packages and has_vite:
        return _result(
            "react-vite",
            package_version(package_json, "react"),
            95,
            "React and Vite packages/config",
        )
    if "vue" in packages and has_vite:
        return _result(
            "vue", package_version(package_json, "vue"), 95, "Vue and Vite packages/config"
        )
    if "vue" in packages or "vue" in topics:
        return _result("vue", package_version(package_json, "vue"), 85, "Vue package/topic")
    if "react" in packages or "react" in topics:
        return _result("react", package_version(package_json, "react"), 80, "React package/topic")

    requirements = (repository.requirements_text or "").casefold()
    pyproject = (repository.pyproject_text or "").casefold()
    if "fastapi" in requirements or "fastapi" in pyproject or "fastapi" in topics:
        return _result("fastapi", None, 95, "FastAPI dependency/topic")
    if (
        "django" in requirements
        or "django" in pyproject
        or "manage.py" in files
        or "django" in topics
    ):
        return _result("django", None, 95, "Django dependency/manage.py/topic")
    if "artisan" in files or "laravel" in topics or "laravel/framework" in packages:
        return _result(
            "laravel",
            package_version(package_json, "laravel/framework"),
            95,
            "Laravel artisan/package/topic",
        )
    if "index.html" in files:
        return _result("static-html", None, 70, "Root index.html")
    if "dockerfile" in files:
        return _result("docker", None, 60, "Root Dockerfile")
    return _result("unknown", None, 0, "No supported framework signature found")


def detect_language(repository: ImportedRepository, detection: FrameworkDetection) -> str | None:
    files = {name.casefold() for name in repository.root_files}
    packages = package_names(repository.package_json)
    if (
        "typescript" in packages
        or "tsconfig.json" in files
        or any(name.endswith(".ts") for name in files)
    ):
        return "TypeScript"
    if detection.slug in {"fastapi", "django"}:
        return "Python"
    if detection.slug == "laravel":
        return "PHP"
    if detection.slug in {"astro", "nextjs", "react-vite", "react", "vue", "nuxt", "sveltekit"}:
        return repository.primary_language or "JavaScript"
    return repository.primary_language
