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
