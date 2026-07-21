# API Contract

The public contract is rooted at `/api/v1`. Only Published templates are visible. List endpoints
are deterministic, bounded, cached, and read-only.

```text
GET /api/v1/templates
GET /api/v1/templates/{slug}
GET /api/v1/templates/{slug}/manifest
GET /api/v1/categories
GET /api/v1/providers
GET /api/v1/frameworks
GET /api/v1/capabilities
GET /api/v1/health
GET /api/v1/ready
```

Manifest v1 remains valid. New Smart Registry imports use Manifest v2. v0.2 adds response fields
such as source adapter, framework version, package manager, preview/screenshots, difficulty, use
case, quality score, analysis, and score breakdown. Existing paths and original fields are not
removed or renamed. Breaking changes require `/api/v2`.

## v0.2.1 additive catalog contract

The legacy v1 endpoints and response shapes remain unchanged. The following endpoints are additive:

```text
GET /api/v1/templates/changes
GET /api/v1/templates/{slug}/assets
GET /api/v1/templates/{slug}/freshness
GET /api/v1/facets
```

Template list accepts additive filters `tag`, `language`, `difficulty`, `use_case`, `min_quality`,
`updated_since`, `sort`, and `order`. Detail and manifest responses support ETag validation.

## v0.2.2 runtime controls and tag fix

The existing v1 response contracts remain unchanged. PostgreSQL tag filtering now uses JSONB
containment and returns normal catalog responses. Runtime Settings may disable the public API or an
individual catalog group. Disabled endpoints return a structured HTTP 503 error containing the
request ID. Health, readiness, and capabilities remain available for diagnosis.

## v0.2.3 API access modes

The endpoint paths and response fields remain backward compatible.

- **Development Mode:** registry endpoints are publicly readable unless disabled by existing feature
  flags or block rules.
- **Live Mode:** registry endpoints, including capabilities, require a scoped service token.
- Health and readiness stay public.

Accepted authentication headers:

```http
Authorization: Bearer vt_reg_xxxxx
X-RegHub-Token: vt_reg_xxxxx
```

Missing, invalid, disabled, or expired credentials return structured HTTP 401 responses with a
request ID and `WWW-Authenticate: Bearer`. Tokens that do not include the endpoint scope are denied.
The CORS policy permits the two authentication headers for configured YGIT origins.
