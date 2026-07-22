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


## v0.3.1.0 stabilization regressions

The release adds regression coverage for roleless legacy-cookie rejection, purpose-key separation,
redirect hardening, complete cookie clearing, fixed OIDC logout targeting, private-repository AI
blocking, deployment-neutral generated manifests, model constraints, and migration safety. Existing
CI gates and retry behavior are unchanged.
