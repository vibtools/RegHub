from typing import Any

from app.registry.adapters.base import ImportedRepository
from app.registry.framework import FrameworkService


def repository(
    *,
    topics: list[str],
    files: set[str],
    package_json: dict[str, Any] | None = None,
) -> ImportedRepository:
    return ImportedRepository(
        adapter="github",
        external_id="1",
        name="demo",
        description=None,
        repository_url="https://github.com/ygit/demo",
        default_branch="main",
        homepage_url=None,
        license_spdx=None,
        topics=topics,
        primary_language=None,
        stars_count=0,
        forks_count=0,
        root_files=frozenset(files),
        package_json=package_json,
        metadata={},
    )


def test_topic_has_priority() -> None:
    assert (
        FrameworkService.detect_slug(repository(topics=["astro"], files={"next.config.js"}))
        == "astro"
    )


def test_detects_root_file() -> None:
    assert (
        FrameworkService.detect_slug(repository(topics=[], files={"next.config.mjs"})) == "nextjs"
    )


def test_detects_astro_from_package_json() -> None:
    package_json = {
        "dependencies": {"astro": "^5.0.0"},
        "devDependencies": {"typescript": "^5.0.0"},
    }
    assert (
        FrameworkService.detect_slug(
            repository(topics=[], files={"package.json"}, package_json=package_json)
        )
        == "astro"
    )


def test_astro_wins_over_react_in_package_json() -> None:
    package_json = {"dependencies": {"react": "^19.0.0", "astro": "^5.0.0"}}
    assert (
        FrameworkService.detect_slug(
            repository(topics=[], files={"package.json"}, package_json=package_json)
        )
        == "astro"
    )
