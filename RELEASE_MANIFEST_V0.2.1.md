# RegHub v0.2.1 Release Manifest

Baseline: RegHub v0.2.0 Smart Registry.

## Preserved

- Keycloak/OIDC authentication and administrator role enforcement
- SQLAdmin CRUD, import, lifecycle, and publication actions
- Draft, Published, Disabled lifecycle
- Existing `/api/v1` response contracts and Manifest v1/v2 support
- PostgreSQL data, Dockerfile, Coolify entrypoint, health/readiness
- Registry-only responsibility; YGIT remains the deployment engine

## Added

- Provider auto-creation from source owner metadata
- Complete import/sync history tracking and historical backfill
- Recursive and README media discovery
- Manual Asset Gallery
- Screenshot job persistence, bounded retry actions, and URL security
- Assets, freshness, changes, facets, filters, sorting, and cache validators

## Migration

`20260721_0003_provider_media_stabilization` follows `20260720_0002` and only adds fields,
indexes, backfill records, and the `screenshot_jobs` table.
