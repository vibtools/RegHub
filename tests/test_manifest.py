import pytest
from pydantic import ValidationError

from app.core.enums import DeployType
from app.registry.manifest import build_manifest, validate_manifest


def test_builds_minimal_manifest() -> None:
    manifest = build_manifest(
        framework_slug="astro",
        repository_url="https://github.com/ygit/starter",
        default_branch="main",
    )
    assert manifest.deploy.type == DeployType.UNKNOWN
    assert manifest.schema_version == "1.0"


def test_manifest_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        validate_manifest(
            {
                "schema_version": "1.0",
                "framework": "astro",
                "repository": "https://github.com/ygit/starter",
                "branch": "main",
                "deploy": {"type": "static", "command": "unsafe"},
            }
        )
