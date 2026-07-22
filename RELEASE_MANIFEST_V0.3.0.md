# RegHub v0.3.0 Production Infrastructure & Governance

## Baseline and compatibility

- Baseline: live `v0.2.3.4 Import Experience Hotfix`.
- Existing `/api/v1` paths, response fields, Settings, Operations, Keycloak login, template IDs,
  slugs, statuses, manifests, provider/media records, service tokens and Coolify entrypoint remain.
- Migration `20260721_0006` is additive. It adds audit-chain storage, operation actor roles and
  catalog indexes; it removes or renames no existing table, column or record.
- The default operation backend remains `inprocess`, so the current single-service Coolify
  deployment remains valid. Redis worker mode is opt-in.

## Production infrastructure

- Optional Redis-backed durable operation queue with a standalone worker process, distributed lock,
  queue reconciliation, worker heartbeat, per-job runtime Settings refresh and restart-safe queued-operation recovery.
- Redis or in-memory catalog cache with generation-based invalidation and fail-open runtime
  degradation to memory.
- Redis or in-memory fixed-window rate limiting for public clients, service tokens and administrator
  sessions.
- Trusted-proxy middleware normalizes forwarding headers only from configured proxy networks.
- Readiness reports operation-worker, cache and rate-limit posture.

## Governance

- Keycloak role mapping for Viewer, Editor, Publisher, Security Admin and Super Admin.
- Legacy `reghub-admin` continues to map to Super Admin, preventing administrator lockout.
- Permission checks protect imports, sync, media, publication, Settings, API security, operation
  management and registry mutations.
- Hash-chained, HMAC-signed immutable audit events record authentication, settings, mutations,
  operations and media changes.
- Dedicated versioned encryption and audit-signing keyrings support safe key rotation while retaining
  the v0.2.x `SESSION_SECRET` decryption fallback.
- Governance dashboard reports effective permissions, audit-chain integrity and infrastructure
  posture.

## Quality gates

- PostgreSQL and Redis integration CI.
- Alembic migration and idempotent seed validation.
- Ruff, compilation, coverage threshold, dependency audit and Docker startup smoke test.
- PostgreSQL JSONB GIN and catalog sort indexes.
