# RegHub v0.2.3 Operations & API Access — Production Audit

## Baseline and zero-freedom compatibility

- Built from the live v0.2.2.1 UI & Operations Hotfix.
- No public API path, OIDC route, SQLAdmin model page, template field, provider/media capability,
  manifest behavior, operation record, runtime integration, Docker entrypoint, or deployment
  boundary was removed.
- Existing template IDs, slugs, publication states, PostgreSQL records, Keycloak values, and Coolify
  variables remain compatible.

## Corrected behavior

- Duplicate repository imports now terminate as `skipped` with a linked existing template and a
  successful Import History no-change record.
- Operation logs include provider, analyzer, resource resolution, transaction, and safe exception
  details in a compact terminal presentation.
- Terminal operation history can be safely cleared without deleting queued or running work.
- Asset Gallery and registry tables include productive search, filters, and sorting.

## Runtime API security

- Development and token-protected Live modes are database-backed and switch immediately.
- Service tokens are scoped, expirable, enable/disable capable, and stored only as HMAC-SHA256
  digests. Raw values are shown once.
- Live API requests accept Bearer or `X-RegHub-Token` authentication.
- IP, CIDR, hostname, localhost, and documented private-network aliases can be blocked at runtime.
- Health/readiness and authenticated administrator recovery surfaces remain available.
- The Settings API checker uses a short-lived in-memory credential and does not persist or display a
  permanent secret.

## Additive database impact

Migration `20260721_0005_api_access_operations` creates three tables only:

- `api_access_policies`
- `api_service_tokens`
- `api_block_rules`

No existing schema object or data is removed or renamed.

## Automated verification

Final release verification results are recorded in `RELEASE_VERIFICATION_V0.2.3.txt` and the
external release audit artifact. Live Coolify, Keycloak, reverse-proxy client-IP forwarding, and
real YGIT token consumption must be verified after deployment.

## Final automated verification

- Automated tests: **85 passed**
- Application statement coverage: **69%**
- Ruff lint and formatting: **PASS**
- Python compilation: **PASS**
- Jinja compilation: **PASS** — 10 templates
- PostgreSQL ORM DDL compilation: **PASS** — 16 tables
- Alembic offline upgrade through `20260721_0005`: **PASS**
- Full FastAPI lifespan, Development Mode, and Live Mode token smoke tests: **PASS**
- Wheel and source distribution build: **PASS**
- Replace-ready ZIP re-extract and full retest: **PASS** — 85 passed
- Dependency integrity and secret-pattern scan: **PASS**
- Baseline source files removed: **0**

One non-blocking Starlette TestClient deprecation warning remains in the test dependency and is not
a production runtime error.
