# RegHub v0.3.2.0 Production Readiness Release

## Baseline

- Source: exported current `hotfix/v0.3.1.2-forensic-release-hardening` working tree.
- Git baseline: `f80a984fce41ff36c82e288d3fd33b3518d32091` plus the uncommitted
  v0.3.1.2 hardening changes contained in the supplied baseline archive.
- Scope: security, release determinism, container integrity, validation and documentation.

## Runtime and API compatibility

- Public `/api/v1` paths: unchanged.
- Database tables, columns and Alembic revisions: unchanged.
- Registry-only service boundary: unchanged.
- Providers, import, sync, publication, assets, Settings and Operations: retained.

## Production hardening

- Production requires distinct session, runtime-encryption and audit-signing keys.
- Production URLs carrying identity or service credentials require HTTPS.
- Public origin, allowed-host and trusted-proxy configuration fail closed.
- Request IDs, forwarding chains and local-manifest URLs are validated before use.
- Local ZIP imports reject control paths, case collisions, symlinks, encryption and size abuse.
- Container startup serializes migration/seed and applies a bounded command timeout.
- Runtime Docker imports the installed wheel instead of a shadow source copy.

## Release gates

- Ruff lint and format.
- Python compilation.
- Static dangerous-call and credential-signature scan.
- SHA-256 verification of the complete release file manifest.
- Release-tree and secure-production configuration verification.
- Single Alembic head, PostgreSQL upgrade and idempotent seed.
- Full pytest with at least 70% application coverage.
- Exact installed dependency snapshot and strict third-party vulnerability audit.
- Non-root, read-only, capability-dropped Docker readiness smoke test.
