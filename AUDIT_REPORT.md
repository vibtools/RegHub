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
