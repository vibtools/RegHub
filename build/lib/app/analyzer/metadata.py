import re

from app.analyzer.framework import FrameworkDetection
from app.registry.adapters.base import ImportedRepository


def title_from_name(name: str) -> str:
    cleaned = re.sub(r"[-_]+", " ", name).strip()
    return re.sub(r"\s+", " ", cleaned).title() or "Untitled Template"


def infer_tags(repository: ImportedRepository, framework_slug: str) -> list[str]:
    tags = {topic.casefold() for topic in repository.topics if topic}
    tags.add(framework_slug)
    text = " ".join(
        filter(None, [repository.name, repository.description or "", repository.readme_text or ""])
    ).casefold()
    keyword_map = {
        "dashboard": "dashboard",
        "saas": "saas",
        "portfolio": "portfolio",
        "blog": "blog",
        "ecommerce": "ecommerce",
        "e-commerce": "ecommerce",
        "shop": "ecommerce",
        "landing": "landing-page",
        "admin": "admin",
        "tailwind": "tailwind",
        "authentication": "auth",
        "auth": "auth",
        "documentation": "docs",
        "cms": "cms",
    }
    for needle, tag in keyword_map.items():
        if needle in text:
            tags.add(tag)
    return sorted(tags)[:20]


def infer_category(tags: list[str]) -> str:
    values = set(tags)
    if {"ecommerce", "shop"} & values:
        return "ecommerce"
    if {"saas", "dashboard", "admin"} & values:
        return "saas"
    if "portfolio" in values:
        return "portfolio"
    if {"blog", "docs", "cms"} & values:
        return "content"
    if "landing-page" in values:
        return "landing-pages"
    return "general"


def infer_use_case(category_slug: str) -> str:
    return {
        "ecommerce": "Online store or commerce website",
        "saas": "SaaS product, dashboard, or admin application",
        "portfolio": "Personal or agency portfolio",
        "content": "Blog, documentation, or content-driven site",
        "landing-pages": "Marketing or campaign landing page",
        "general": "General web application starter",
    }.get(category_slug, "General web application starter")


def infer_difficulty(repository: ImportedRepository) -> str:
    package_count = 0
    if isinstance(repository.package_json, dict):
        for section in ("dependencies", "devDependencies"):
            values = repository.package_json.get(section)
            if isinstance(values, dict):
                package_count += len(values)
    if repository.dockerfile_text or package_count >= 35:
        return "advanced"
    if package_count >= 12 or repository.env_example_text:
        return "intermediate"
    return "beginner"


def descriptions(
    repository: ImportedRepository, title: str, detection: FrameworkDetection
) -> tuple[str | None, str | None]:
    base = (repository.description or "").strip()
    if base:
        short = base[:320]
        return short, base
    short = f"{detection.name} template imported from {repository.repository_url}."
    readme = (repository.readme_text or "").strip()
    description = readme[:2000] if readme else short
    return short, description
