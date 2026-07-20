from app.core.enums import DeployType
from app.schemas.manifest import DeployManifest, TemplateManifest

_DEPLOY_TYPE_BY_FRAMEWORK = {
    "astro": DeployType.STATIC,
    "static-html": DeployType.STATIC,
    "react": DeployType.NODE,
    "vue": DeployType.NODE,
    "nextjs": DeployType.NODE,
    "nuxt": DeployType.NODE,
    "sveltekit": DeployType.NODE,
    "fastapi": DeployType.PYTHON,
    "django": DeployType.PYTHON,
    "laravel": DeployType.PHP,
    "docker": DeployType.DOCKER,
}


def build_manifest(
    *, framework_slug: str, repository_url: str, default_branch: str
) -> TemplateManifest:
    return TemplateManifest(
        framework=framework_slug,
        repository=repository_url,
        branch=default_branch,
        deploy=DeployManifest(type=_DEPLOY_TYPE_BY_FRAMEWORK.get(framework_slug, DeployType.UNKNOWN)),
    )


def validate_manifest(value: dict[str, object]) -> TemplateManifest:
    return TemplateManifest.model_validate(value)
