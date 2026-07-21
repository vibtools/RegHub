from app.analyzer.models import AnalysisResult
from app.core.enums import DeployType
from app.schemas.manifest import BuildManifest, DeployManifest, TemplateManifest

_DEPLOY_TYPE_BY_FRAMEWORK = {
    "astro": DeployType.STATIC,
    "static-html": DeployType.STATIC,
    "react-vite": DeployType.STATIC,
    "react": DeployType.NODE,
    "vue": DeployType.STATIC,
    "nextjs": DeployType.NODE,
    "nuxt": DeployType.NODE,
    "sveltekit": DeployType.NODE,
    "fastapi": DeployType.PYTHON,
    "django": DeployType.PYTHON,
    "laravel": DeployType.PHP,
    "docker": DeployType.DOCKER,
}


def build_manifest(
    *,
    framework_slug: str,
    repository_url: str,
    default_branch: str,
    name: str | None = None,
    analysis: AnalysisResult | None = None,
    schema_version: str = "1.0",
) -> TemplateManifest:
    deploy_type = (
        DeployType(analysis.deploy_type)
        if analysis
        else _DEPLOY_TYPE_BY_FRAMEWORK.get(framework_slug, DeployType.UNKNOWN)
    )
    if schema_version == "1.0":
        return TemplateManifest(
            schema_version="1.0",
            framework=framework_slug,
            repository=repository_url,
            branch=default_branch,
            deploy=DeployManifest(type=deploy_type),
        )
    return TemplateManifest(
        schema_version="2.0",
        name=name or (analysis.title if analysis else "Template"),
        framework=framework_slug,
        framework_version=analysis.framework_version if analysis else None,
        language=analysis.language if analysis else None,
        package_manager=analysis.package_manager if analysis else None,
        repository=repository_url,
        branch=default_branch,
        build=BuildManifest(
            command=analysis.build_command if analysis else None,
            start_command=analysis.start_command if analysis else None,
        ),
        deploy=DeployManifest(type=deploy_type),
        environment=analysis.environment if analysis else [],
    )


def validate_manifest(value: dict[str, object]) -> TemplateManifest:
    return TemplateManifest.model_validate(value)
