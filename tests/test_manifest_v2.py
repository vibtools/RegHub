import pytest
from pydantic import ValidationError

from app.analyzer.models import AnalysisResult
from app.registry.manifest import build_manifest, validate_manifest


def analysis() -> AnalysisResult:
    return AnalysisResult(
        framework_slug="astro",
        framework_name="Astro",
        framework_version="5.2.1",
        language="TypeScript",
        package_manager="pnpm",
        title="Astro Starter",
        short_description="Starter",
        description="Starter",
        tags=["astro"],
        category_slug="general",
        difficulty="beginner",
        use_case="General web application starter",
    )


def test_builds_manifest_v2() -> None:
    manifest = build_manifest(
        framework_slug="astro",
        repository_url="https://github.com/ygit/starter",
        default_branch="main",
        name="Astro Starter",
        analysis=analysis(),
        schema_version="2.0",
    )
    assert manifest.schema_version == "2.0"
    assert manifest.name == "Astro Starter"
    assert manifest.framework_version == "5.2.1"
    assert manifest.build is None
    assert manifest.deploy.type.value == "unknown"
    assert manifest.environment == []


def test_v1_remains_valid() -> None:
    manifest = validate_manifest(
        {
            "schema_version": "1.0",
            "framework": "astro",
            "repository": "https://github.com/ygit/starter",
            "branch": "main",
            "deploy": {"type": "static"},
        }
    )
    assert manifest.schema_version == "1.0"


def test_v2_requires_name() -> None:
    with pytest.raises(ValidationError):
        validate_manifest(
            {
                "schema_version": "2.0",
                "framework": "astro",
                "repository": "https://github.com/ygit/starter",
                "branch": "main",
                "deploy": {"type": "static"},
            }
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://gitlab.com/group/repo",
        "https://bitbucket.org/team/repo",
        "local://manifest/123",
    ],
)
def test_v2_supports_registry_sources(url: str) -> None:
    value = validate_manifest(
        {
            "schema_version": "2.0",
            "name": "Demo",
            "framework": "unknown",
            "repository": url,
            "branch": "main",
            "deploy": {"type": "unknown"},
        }
    )
    assert value.repository == url
