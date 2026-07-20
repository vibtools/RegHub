from app.registry.adapters.base import ImportedRepository
from app.registry.framework import FrameworkService


def repository(*, topics: list[str], files: set[str]) -> ImportedRepository:
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
        metadata={},
    )


def test_topic_has_priority() -> None:
    assert FrameworkService.detect_slug(repository(topics=["astro"], files={"next.config.js"})) == "astro"


def test_detects_root_file() -> None:
    assert FrameworkService.detect_slug(repository(topics=[], files={"next.config.mjs"})) == "nextjs"
