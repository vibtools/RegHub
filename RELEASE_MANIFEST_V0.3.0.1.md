# RegHub v0.3.0.1 Governance UI & Redis Worker Control Hotfix

## Baseline

- Baseline: v0.3.0 Production Infrastructure & Governance.
- Existing APIs, Settings, Operations, Keycloak RBAC, audit history, service tokens, templates,
  migrations, Coolify boundaries, and in-process execution remain intact.

## Corrections

- `/admin/governance` now renders inside `reghub_layout.html` through `reghub_content`, preventing
  SQLAdmin row shrinkage and horizontal overflow.
- The governance page now provides responsive posture cards and safe wrapping for long values.
- Settings → Feature controls includes `redis_worker`.
- The runtime switch sends new operations to Redis only after Redis and a worker heartbeat validate.
- OFF uses the existing in-process runner. Previously queued Redis jobs are drained safely.
- Readiness and capabilities expose the effective operation backend.

## Database

No migration. Runtime feature initialization adds the new feature-flag row idempotently.
