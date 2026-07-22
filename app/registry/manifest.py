from app.analyzer.models import AnalysisResult
from app.core.enums import DeployType
from app.schemas.manifest import DeployManifest, TemplateManifest


def build_manifest(
    *,
    framework_slug: str,
    repository_url: str,
    default_branch: str,
    name: str | None = None,
    analysis: AnalysisResult | None = None,
    schema_version: str = "1.0",
) -> TemplateManifest:
    """Build a registry manifest without generating deployment recommendations.

    The manifest schema remains backward compatible, but RegHub records an unknown deployment type
    unless a separately supplied manifest explicitly declares deployment data. YGIT owns build,
    start, runtime and deployment decisions.
    """

    if schema_version == "1.0":
        return TemplateManifest(
            schema_version="1.0",
            framework=framework_slug,
            repository=repository_url,
            branch=default_branch,
            deploy=DeployManifest(type=DeployType.UNKNOWN),
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
        deploy=DeployManifest(type=DeployType.UNKNOWN),
    )


def validate_manifest(value: dict[str, object]) -> TemplateManifest:
    return TemplateManifest.model_validate(value)
