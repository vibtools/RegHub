from datetime import UTC, datetime

from app.registry.adapters.base import ImportedRepository


def calculate_quality(
    repository: ImportedRepository,
    *,
    framework_detected: bool,
    environment_count: int,
    screenshot_count: int,
    security_signal_count: int,
    build_ready: bool,
) -> tuple[int, dict[str, int]]:
    breakdown = {
        "documentation": 15
        if repository.readme_text and len(repository.readme_text.strip()) >= 300
        else (7 if repository.readme_text else 0),
        "license": 10 if repository.license_spdx else 0,
        "framework": 15 if framework_detected else 0,
        "environment": 8 if repository.env_example_text or environment_count else 0,
        "visual_preview": 8 if screenshot_count else (4 if repository.homepage_url else 0),
        "deployment_readiness": 12 if build_ready else (6 if repository.dockerfile_text else 0),
        "security": max(0, 10 - security_signal_count * 3),
        "community": min(10, (repository.stars_count // 10) + min(5, repository.forks_count)),
        "freshness": 12,
    }
    updated = repository.source_updated_at
    if updated:
        now = datetime.now(UTC)
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=UTC)
        days = max(0, (now - updated).days)
        breakdown["freshness"] = 12 if days <= 180 else (7 if days <= 730 else 2)
    total = max(0, min(100, sum(breakdown.values())))
    return total, breakdown
