from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote


@dataclass(frozen=True, slots=True)
class ApiEndpointDefinition:
    key: str
    name: str
    method: str
    path_template: str
    scope: str | None
    description: str
    public_always: bool = False
    requires_template: bool = False

    def concrete_path(self, template_slug: str | None) -> str | None:
        if not self.requires_template:
            return self.path_template
        if not template_slug:
            return None
        return self.path_template.replace("{slug}", quote(template_slug, safe=""))


API_ENDPOINTS: tuple[ApiEndpointDefinition, ...] = (
    ApiEndpointDefinition(
        key="health",
        name="Health",
        method="GET",
        path_template="/api/v1/health",
        scope=None,
        description="Process health probe. Always public, including Live Mode.",
        public_always=True,
    ),
    ApiEndpointDefinition(
        key="ready",
        name="Readiness",
        method="GET",
        path_template="/api/v1/ready",
        scope=None,
        description="Database readiness probe. Always public, including Live Mode.",
        public_always=True,
    ),
    ApiEndpointDefinition(
        key="capabilities",
        name="Capabilities",
        method="GET",
        path_template="/api/v1/capabilities",
        scope="capabilities",
        description="Registry version, adapters and runtime capability flags.",
    ),
    ApiEndpointDefinition(
        key="templates",
        name="Template catalog",
        method="GET",
        path_template="/api/v1/templates?page=1&page_size=20&sort=updated&order=desc",
        scope="catalog",
        description="Published template list with search, filters, pagination and sorting.",
    ),
    ApiEndpointDefinition(
        key="template_changes",
        name="Template change feed",
        method="GET",
        path_template=(
            "/api/v1/templates/changes?updated_since=2000-01-01T00%3A00%3A00Z&page=1&page_size=20"
        ),
        scope="changes",
        description="Incremental published-template updates for consumers such as YGIT.",
    ),
    ApiEndpointDefinition(
        key="categories",
        name="Categories",
        method="GET",
        path_template="/api/v1/categories",
        scope="catalog",
        description="Active registry categories.",
    ),
    ApiEndpointDefinition(
        key="providers",
        name="Providers",
        method="GET",
        path_template="/api/v1/providers",
        scope="catalog",
        description="Active source providers and organizations.",
    ),
    ApiEndpointDefinition(
        key="frameworks",
        name="Frameworks",
        method="GET",
        path_template="/api/v1/frameworks",
        scope="catalog",
        description="Active framework definitions.",
    ),
    ApiEndpointDefinition(
        key="facets",
        name="Catalog facets",
        method="GET",
        path_template="/api/v1/facets",
        scope="facets",
        description="Filter counts for category, provider, framework, language and difficulty.",
    ),
    ApiEndpointDefinition(
        key="template_detail",
        name="Template detail",
        method="GET",
        path_template="/api/v1/templates/{slug}",
        scope="catalog",
        description="Full published-template metadata.",
        requires_template=True,
    ),
    ApiEndpointDefinition(
        key="template_manifest",
        name="Template manifest",
        method="GET",
        path_template="/api/v1/templates/{slug}/manifest",
        scope="catalog",
        description="Manifest v1/v2 payload consumed by the deployment engine.",
        requires_template=True,
    ),
    ApiEndpointDefinition(
        key="template_assets",
        name="Template assets",
        method="GET",
        path_template="/api/v1/templates/{slug}/assets",
        scope="assets",
        description="Published screenshots, thumbnails and media assets.",
        requires_template=True,
    ),
    ApiEndpointDefinition(
        key="template_freshness",
        name="Template freshness",
        method="GET",
        path_template="/api/v1/templates/{slug}/freshness",
        scope="freshness",
        description="Source revision, sync status and stale-state information.",
        requires_template=True,
    ),
)


def endpoint_rows(template_slug: str | None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for endpoint in API_ENDPOINTS:
        concrete = endpoint.concrete_path(template_slug)
        rows.append(
            {
                "key": endpoint.key,
                "name": endpoint.name,
                "method": endpoint.method,
                "path_template": endpoint.path_template,
                "check_path": concrete,
                "scope": endpoint.scope,
                "description": endpoint.description,
                "public_always": endpoint.public_always,
                "requires_template": endpoint.requires_template,
                "checkable": concrete is not None,
            }
        )
    return rows


def endpoint_by_key(key: str) -> ApiEndpointDefinition | None:
    return next((item for item in API_ENDPOINTS if item.key == key), None)
