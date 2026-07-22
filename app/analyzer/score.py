from datetime import UTC, datetime

from app.registry.adapters.base import ImportedRepository


def calculate_quality(
    repository: ImportedRepository,
    *,
    framework_detected: bool,
    screenshot_count: int,
    security_signal_count: int,
) -> tuple[int, dict[str, int]]:
    package_metadata_present = bool(
        repository.package_json or repository.requirements_text or repository.pyproject_text
    )
    root_files_present = bool(repository.root_files)
    metadata_score = (
        (4 if repository.description else 0)
        + (4 if repository.topics else 0)
        + (4 if repository.primary_language else 0)
    )
    structure_score = (
        8 if root_files_present and package_metadata_present else (4 if root_files_present else 0)
    )
    breakdown = {
        "documentation": 15
        if repository.readme_text and len(repository.readme_text.strip()) >= 300
        else (7 if repository.readme_text else 0),
        "license": 10 if repository.license_spdx else 0,
        "framework": 15 if framework_detected else 0,
        "metadata": metadata_score,
        "visual_preview": 8 if screenshot_count else (4 if repository.homepage_url else 0),
        "repository_structure": structure_score,
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
