# RegHub

Current release: **v0.1.1**

RegHub is the registry service for the YGIT ecosystem. It manages template metadata and
publishes a stable read-only API for `ygit.net`. It does **not** build or deploy projects.

## Fixed service boundaries

- Identity: `auth.vib.tools`
- Registry: `reghub.ygit.dev`
- Deployment: `ygit.net`
- Repository metadata: GitHub API
- Hosting: Coolify

## MVP features

- OIDC administrator login through `auth.vib.tools`
- SQLAdmin internal registry panel
- GitHub API metadata import without repository cloning
- Optional server-side fine-grained GitHub PAT with clear authenticated status
- Astro auto-detection from topics, Astro config files, and root `package.json`
- Templates, categories, providers, and frameworks
- Draft, published, and disabled lifecycle
- Versioned public read-only API
- Minimal, validated deployment manifest served to YGIT
- PostgreSQL/Alembic, Docker, tests, health checks

## Local setup

```bash
cp .env.local.example .env
# Set SESSION_SECRET to a random value of at least 32 characters.
docker compose -f compose.local.yml up --build
```

Open:

- API documentation: `http://localhost:8000/docs`
- Admin panel: `http://localhost:8000/admin`
- Health: `http://localhost:8000/api/v1/health`

When OIDC is not configured, `/admin` remains locked. Configure the client in
`auth.vib.tools` with callback URL:

```text
https://reghub.ygit.dev/auth/callback
```

## Coolify

Deploy this repository as a Dockerfile application. Configure the domain
`reghub.ygit.dev`, attach PostgreSQL, and copy the production variables described in
`docs/09_COOLIFY_DEPLOYMENT.md` into Coolify Secrets.

## Public API

```text
GET /api/v1/templates
GET /api/v1/templates/{slug}
GET /api/v1/templates/{slug}/manifest
GET /api/v1/categories
GET /api/v1/providers
GET /api/v1/frameworks
```

Only published templates are exposed. YGIT owns all deployment behavior.

## v0.1.1 production patch

- Fixes the SQLAdmin Templates list crash caused by SQLAdmin 0.29 filter API changes.
- Preserves Status, Featured, and Framework filters using supported filter objects.
- Improves GitHub token errors and shows authenticated/unauthenticated API mode.
- Reads a bounded root `package.json` through GitHub's API for framework detection.
- Adds Astro detection regression coverage without cloning or executing repositories.
- Requires no database migration and does not change existing public API paths.
