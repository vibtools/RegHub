# RegHub v0.3.1.2 Forensic Release Hardening Hotfix

Baseline: `f80a984fce41ff36c82e288d3fd33b3518d32091`

This is a zero-feature, zero-schema release-hardening hotfix.

## Corrected

- Rejects the known development session secret in production.
- Requires HTTPS public and OIDC issuer URLs in production.
- Rejects wildcard trusted-proxy configuration in production.
- Serializes migration and seed startup across concurrent containers with a PostgreSQL advisory lock.
- Uses readiness, not process-only liveness, for Docker and CI container health.
- Adds `pip check`, a single Alembic-head gate, and a deterministic third-party dependency audit snapshot.
- Excludes only the private `reghub` distribution from public vulnerability-index lookup.
- Keeps strict dependency auditing enabled.

## Compatibility

- Public API routes: unchanged.
- Database tables/columns: unchanged.
- Alembic migration chain: unchanged; no new migration.
- Runtime dependencies: unchanged.
- Registry/import/publishing/admin behavior: unchanged.
- Deployment remains Docker/Coolify based.
