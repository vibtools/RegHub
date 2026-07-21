# RegHub

Current release: **v0.2.1 Stabilization, Provider & Media Fix**

RegHub is the registry service for the YGIT ecosystem. It imports and analyzes template metadata,
manages publication, and serves a stable read-only API to `ygit.net`. RegHub does **not** build or
deploy user projects.

## Fixed service boundaries

- Identity: `auth.vib.tools` / Keycloak
- Registry: `reghub.ygit.dev`
- Deployment: `ygit.net`
- Repository sources: GitHub, GitLab, Bitbucket, local manifest/ZIP
- Hosting: Coolify

## v0.2.1 features

- All v0.2.0 Smart Registry features preserved
- GitHub/GitLab/Bitbucket owner-based Provider auto-creation
- Initial import and manual sync audit records with change summaries
- Existing-template Sync History backfill migration
- Recursive provider media discovery and README image detection
- Manual Asset Gallery with add, edit, delete, ordering, and thumbnail selection
- Tracked screenshot jobs with safe HTTPS validation and failure history
- Manual and generated assets preserved during source synchronization
- Public assets, freshness, change-feed, and facets API endpoints
- Extended filters and sorting while preserving all existing v1 response contracts
- ETag and Last-Modified headers for detail and manifest endpoints

## Security model

RegHub reads bounded metadata through provider APIs. It does not clone repositories, install
packages, run builds, start templates, or execute uploaded code. Screenshot capture remains delegated
to an isolated external service. Preview and screenshot URLs must be public HTTPS URLs. RegHub rejects credentials, custom ports,
blocked hostnames, and literal private/reserved addresses; the isolated screenshot service must also
enforce DNS-resolution and outbound-network restrictions.

## Public API

Existing endpoints remain compatible:

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

Additive v0.2.1 endpoints:

```text
GET /api/v1/templates/changes?updated_since=<ISO-8601>
GET /api/v1/templates/{slug}/assets
GET /api/v1/templates/{slug}/freshness
GET /api/v1/facets
```

Additional template filters:

```text
tag, language, difficulty, use_case, min_quality, updated_since, sort, order
```

Only Published templates are exposed.

## Coolify upgrade

1. Take a PostgreSQL backup.
2. Replace project files while preserving `.git` and any local `.env`.
3. Commit and push to `main`.
4. Redeploy in Coolify.
5. The entrypoint runs `alembic upgrade head` and `python -m scripts.seed` automatically.
6. Verify health, readiness, admin sync, providers, asset gallery, and public APIs.

See `docs/15_V0.2.1_UPGRADE.md` and `docs/16_V0.2.1_API.md`.
