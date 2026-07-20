from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.models.framework import Framework
from app.models.template import Template
from app.registry.manifest import build_manifest
from app.registry.publishing import validate_template_for_publication


def make_template() -> Template:
    framework = Framework(id=uuid4(), name="Astro", slug="astro", is_active=True)
    manifest = build_manifest(
        framework_slug="astro",
        repository_url="https://github.com/ygit/demo",
        default_branch="main",
    )
    return Template(
        name="Demo",
        slug="demo",
        repository_url="https://github.com/ygit/demo",
        default_branch="main",
        manifest=manifest.model_dump(mode="json"),
        topics=[],
        framework=framework,
        framework_id=framework.id,
    )


def test_valid_template_can_be_published() -> None:
    validate_template_for_publication(make_template())


def test_repository_mismatch_is_rejected() -> None:
    template = make_template()
    template.repository_url = "https://github.com/ygit/other"
    with pytest.raises(ValidationError, match="repository"):
        validate_template_for_publication(template)


def test_framework_mismatch_is_rejected() -> None:
    template = make_template()
    template.framework.slug = "nextjs"
    with pytest.raises(ValidationError, match="framework"):
        validate_template_for_publication(template)
