from app.core.exceptions import ValidationError
from app.models.template import Template
from app.registry.manifest import validate_manifest


def validate_template_for_publication(template: Template) -> None:
    if template.framework_id is None or template.framework is None:
        raise ValidationError(f"{template.name} needs a framework before publishing")
    if template.repository_url.startswith("local://"):
        raise ValidationError(
            f"{template.name} needs a deployable HTTPS repository before publishing"
        )
    manifest = validate_manifest(template.manifest)
    if manifest.repository != template.repository_url:
        raise ValidationError(f"{template.name} manifest repository does not match the template")
    if manifest.branch != template.default_branch:
        raise ValidationError(f"{template.name} manifest branch does not match the template")
    if manifest.framework != template.framework.slug:
        raise ValidationError(f"{template.name} manifest framework does not match the template")
