# RegHub v0.3.2.0 Production Readiness Forensic Audit

- Baseline: supplied v0.3.2.0 current-baseline export from the v0.3.1.2 forensic branch.
- Hidden delivery files omitted by the exporter were reconstructed from Git commit `f80a984`.
- Public API routes, database schema, migration graph and registry/deployment ownership are preserved.
- Production secrets, origins, hosts, proxies and optional service endpoints now fail closed.
- Request/proxy/local-import trust boundaries received dedicated regression coverage.
- Docker now executes the installed wheel and CI tests a restricted non-root runtime.
- Promotion remains blocked until complete dependency-installed GitHub Actions and deployment checks pass.

# RegHub v0.3.1.2 Forensic Release Hardening Audit

- Baseline: `f80a984fce41ff36c82e288d3fd33b3518d32091`.
- Classification: zero-feature, zero-schema production and release hardening hotfix.
- Security: production fails closed for the development session secret, insecure public/OIDC URLs and
  wildcard proxy trust.
- Startup: migration and seed execution is serialized across replicas with a PostgreSQL advisory lock.
- Delivery: dependency consistency, one Alembic head, strict third-party audit and readiness-based
  Docker health are mandatory.
- Public API, database schema, runtime dependencies and registry behavior: unchanged.

# RegHub v0.3.1.1 Final Stabilization Hotfix Audit

- Baseline: v0.3.1.0 release commit.
- Classification: final stabilization hotfix; no feature or architecture work.
- Repository: stale `build/`/`dist/`, generated root reports and dead placeholder integrations removed.
- Database: data-only migration `20260722_0008` normalizes current and historical analysis JSON.
- Registry analysis: framework, language, package manager, license, README, topics and repository
  metadata remain unchanged.
- Public API, admin, OIDC, publication, import, sync, assets and manifests: unchanged.
- Dockerfile, GitHub Actions, entrypoint and Coolify deployment workflow: unchanged.

# RegHub v0.3.1.0 Architecture Stabilization Audit

- Baseline: v0.3.0.3 replace-ready source plus the current main-branch Ruff-only formatting commit.
- Classification: Architecture Stabilization Release; no feature work.
- Public endpoints added/removed: none.
- Integrations, providers, admin pages, Settings, services, deployment and CI workflow changes: none.
- Security: roleless legacy cookies rejected; purpose-bound key separation; complete local/OIDC logout;
  private repository AI processing blocked at both orchestration and transport boundaries.
- Registry boundary: framework/language/package/license/topic/README/repository analysis retained;
  generated build/start/runtime/environment/deployment intelligence removed.
- Database: additive migration `20260722_0007`; no table or column removed; exact duplicate assets
  cleaned; constraints/model lengths aligned; redundant indexes removed.
- Repository: build/cache/generated historical report noise removed from the release source.
- Existing replace, Git push, and Coolify deployment workflow preserved.

# RegHub v0.3.0.1 Hotfix Audit

- Baseline: v0.3.0 replace-ready source.
- Governance page shared-layout regression: corrected.
- Redis worker runtime feature control: added with connectivity and heartbeat validation.
- Existing queued Redis operations drain after switch-off; new operations use in-process execution.
- Database migration: none.
- Existing source files removed: none.

# RegHub v0.3.0 Master Production Audit

## Baseline integrity

- Baseline: live v0.2.3.4 source.
- Existing baseline files removed: 0.
- Existing `/api/v1`, OIDC, SQLAdmin, Settings, Operations, template lifecycle, manifests, provider
  adapters, assets, API service tokens and Coolify boundaries are preserved.
- Migration `20260721_0006` is additive.

## Corrected production gaps

1. **Operation durability:** optional Redis queue/worker added without changing the compatible
   in-process default.
2. **Proxy trust:** forwarding headers are interpreted only for configured proxy peers; Uvicorn no
   longer trusts every forwarding header.
3. **Abuse control:** public, token, token-IP and administrator quotas are available with Redis/shared
   or memory fallback.
4. **Authorization:** granular Keycloak roles and action-level permissions replace all-or-nothing
   administration while preserving legacy administrator access.
5. **Accountability:** authentication, Settings, mutations, media and operation outcomes enter a
   signed immutable audit chain.
6. **Secret governance:** runtime credentials and audit signatures use versioned independent
   keyrings with previous-key compatibility.
7. **Catalog scale:** Redis/memory cache and PostgreSQL catalog/JSONB indexes reduce repeated queries.
8. **Release governance:** CI now validates PostgreSQL, Redis, migrations, seed, coverage, dependency
   security and the Docker startup path.

## Safety posture

- RegHub remains registry-only and never executes imported code.
- Redis is optional on first rollout.
- Existing v0.2.x credentials remain decryptable when `SESSION_SECRET` is unchanged.
- Operation retries enforce the original operation permission; users cannot replay a higher-privilege
  operation through the Operations Console.
- Audit rows are read-only in the administrator UI and remain after terminal operation history is
  cleared.

## Verification performed in the build workspace

- Dependency-independent automated tests: **59 passed**.
- Python compilation: **PASS**.
- Jinja template compilation: **PASS** (11 templates).
- YAML parsing: **PASS** (`compose.local.yml` and production CI).
- Shell entrypoint syntax: **PASS**.
- Production-compatible Settings validation: **PASS**.
- PostgreSQL model DDL compilation: **PASS** (18 tables, 76 indexes).
- Alembic PostgreSQL offline upgrade through `20260721_0006`: **PASS**.
- Audit chain hash, key rotation, nested redaction and tail-state detection smoke tests: **PASS**.
- Redis/memory cache, rate-limit and trusted-proxy governance tests: **PASS**.
- Python wheel build: **PASS**.
- Git diff whitespace validation: **PASS**.

The build environment did not provide all locked application/dev dependencies (`sqladmin`, Authlib,
PyGithub, python-slugify, aiosqlite and Ruff), and its package gateway did not expose them. Therefore,
the complete dependency-installed pytest and Ruff suites could not be rerun locally. The included
GitHub CI installs the complete dependency set and blocks promotion unless Ruff, formatting, full
pytest coverage, PostgreSQL/Redis integration, Alembic, dependency audit and Docker smoke all pass.
Deployment-time verification remains required for Coolify, Keycloak, real provider credentials and
the optional Redis worker.
