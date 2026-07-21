# RegHub v0.2.0 Release Manifest

Baseline: RegHub v0.1.1 replace-ready release.

## Preserved

- Keycloak/OIDC login and administrator claim enforcement
- SQLAdmin CRUD and publication actions
- Draft, Published, Disabled lifecycle
- Public `/api/v1` catalog endpoints
- PostgreSQL, Alembic, Dockerfile, Coolify entrypoint, health/readiness
- Existing database records and Manifest v1 validation
- Registry-only responsibility boundary

## Added

- Smart analyzer engine
- GitHub/GitLab/Bitbucket adapters
- Local manifest and secure ZIP inspection
- Manifest v2
- Quality scoring
- Source synchronization
- Version/sync/asset storage
- Optional AI and screenshot integrations
- Capabilities API

## Migration

`20260720_0002_smart_registry` is additive and follows `20260720_0001`.
