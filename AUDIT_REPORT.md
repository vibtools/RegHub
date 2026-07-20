# RegHub v0.1.1 — Audit Report

## Baseline

The user-supplied running RegHub v0.1.0 archive was used as the authoritative baseline.
No existing feature, endpoint, model field, migration, authentication flow, or deployment
boundary was removed.

## Root cause fixed

`/admin/template/list` failed because SQLAdmin 0.29 expects filter objects with a
`parameter_name` attribute. v0.1.0 supplied raw SQLAlchemy attributes in `column_filters`,
causing an `AttributeError` before the page rendered.

v0.1.1 uses supported `StaticValuesFilter`, `BooleanFilter`, and `ForeignKeyFilter` objects
and preserves the original Status, Featured, and Framework filters.

## GitHub and Astro improvements

- Existing `GITHUB_TOKEN` support was retained and made observable in the admin import UI.
- Bad credentials and rate-limit failures now return actionable, non-secret messages.
- A bounded root `package.json` is read through the GitHub Contents API.
- No repository is cloned, installed, built, or executed.
- Astro is detected from topics, `astro.config.js/mjs/ts/cjs`, or the `astro` dependency.
- Astro has priority over React when an Astro project uses the React integration.

## Compatibility

- Database migration: none.
- Existing migration history: unchanged.
- Existing database data: preserved.
- Keycloak/OIDC: unchanged.
- Public API paths and schemas: unchanged.
- Template manifest schema: unchanged at v1.0.
- Coolify Dockerfile and entrypoint behavior: unchanged.

## Automated verification

- Unit and integration tests: 22 passed.
- SQLAdmin Template list regression: passed.
- SQLAdmin Status and Featured filter requests: passed.
- Astro package detection tests: passed.
- GitHub PAT wiring test: passed.
- Package metadata size-bound tests: passed.
- Python compile check: passed.
- Targeted Ruff checks for all changed logic: passed.

## Environment limitation

A Docker daemon and the user's live Coolify, PostgreSQL, Keycloak, and GitHub environment
were not available in the artifact runtime. Production verification steps are documented in
`docs/12_V0.1.1_UPDATE.md`.
