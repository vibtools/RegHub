from typing import Any

import pytest

from app.analyzer.framework import detect_framework, detect_language
from app.analyzer.package import detect_package_manager
from app.registry.adapters.base import ImportedRepository


def repo(
    *,
    files: set[str] | None = None,
    package_json: dict[str, Any] | None = None,
    requirements: str | None = None,
    pyproject: str | None = None,
    language: str | None = None,
) -> ImportedRepository:
    return ImportedRepository(
        adapter="github",
        external_id="1",
        name="demo",
        description=None,
        repository_url="https://github.com/ygit/demo",
        default_branch="main",
        homepage_url=None,
        license_spdx="MIT",
        topics=[],
        primary_language=language,
        stars_count=0,
        forks_count=0,
        root_files=frozenset(files or set()),
        package_json=package_json,
        metadata={},
        requirements_text=requirements,
        pyproject_text=pyproject,
    )


@pytest.mark.parametrize(
    ("package_json", "files", "expected", "version"),
    [
        ({"dependencies": {"astro": "^5.2.1"}}, {"package.json"}, "astro", "5.2.1"),
        ({"dependencies": {"next": "15.1.0"}}, {"package.json"}, "nextjs", "15.1.0"),
        (
            {"dependencies": {"react": "19.0.0"}, "devDependencies": {"vite": "6.0.0"}},
            {"package.json", "vite.config.ts"},
            "react-vite",
            "19.0.0",
        ),
        ({"dependencies": {"vue": "^3.5.0"}}, {"package.json"}, "vue", "3.5.0"),
        ({"dependencies": {"nuxt": "^3.15.0"}}, {"package.json"}, "nuxt", "3.15.0"),
        (
            {"devDependencies": {"@sveltejs/kit": "^2.10.0"}},
            {"package.json", "svelte.config.js"},
            "sveltekit",
            "2.10.0",
        ),
    ],
)
def test_detects_javascript_frameworks(package_json, files, expected, version) -> None:
    detection = detect_framework(repo(files=files, package_json=package_json))
    assert detection.slug == expected
    assert detection.version == version


def test_detects_fastapi_from_requirements() -> None:
    assert detect_framework(repo(requirements="fastapi==0.115\nuvicorn")).slug == "fastapi"


def test_detects_django_from_manage_py() -> None:
    assert detect_framework(repo(files={"manage.py"})).slug == "django"


def test_detects_typescript() -> None:
    repository = repo(
        files={"package.json", "tsconfig.json"},
        package_json={"devDependencies": {"typescript": "5.7.0"}},
    )
    assert detect_language(repository, detect_framework(repository)) == "TypeScript"


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ({"pnpm-lock.yaml", "package.json"}, "pnpm"),
        ({"yarn.lock", "package.json"}, "yarn"),
        ({"bun.lockb", "package.json"}, "bun"),
        ({"package-lock.json", "package.json"}, "npm"),
        ({"poetry.lock", "pyproject.toml"}, "poetry"),
    ],
)
def test_detects_package_manager(files, expected) -> None:
    assert detect_package_manager(frozenset(files)) == expected
