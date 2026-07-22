# Test Strategy

## Unit and regression

- analyzers, manifests, provider URLs, import/sync, Settings, Operations and API behavior;
- RBAC role/permission mapping and legacy cookie compatibility;
- versioned encryption/audit keyrings and nested secret redaction;
- cache generation, rate limits and trusted-proxy normalization;
- immutable audit-chain tamper detection.

## Integration

GitHub Actions starts PostgreSQL and Redis, upgrades Alembic, runs the idempotent seed and executes
the test suite with a 70% application coverage floor.

## Delivery

CI also runs Ruff, Python compilation, dependency vulnerability audit, Docker image build, container
startup and health verification. Live deployment verification still covers Keycloak, provider
credentials, Coolify proxy networks, worker heartbeat, backups and rollback.
