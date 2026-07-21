# RegHub v0.2.3.3 Settings Action & UI Responsiveness Hotfix — Master Audit

## Baseline and zero-freedom compatibility

- Built directly from the live v0.2.3.2 replace-ready archive.
- Baseline source files removed: **0**.
- Existing public API routes, administrator pages, OIDC/Keycloak behavior, runtime feature flags,
  integration records, encrypted credentials, API service tokens, block rules, template records,
  operation history, Docker entrypoint, Coolify variables, and deployment boundaries are preserved.
- Database revision remains `20260721_0005`; this hotfix includes no Alembic migration.

## Production incident finding

The live deployment returned HTTP 404 when Settings mutations were sent to the same mixed GET/POST
page URL used to render `/admin/settings`. The route is accepted by the local SQLAdmin test stack,
but the deployed route/proxy combination did not reliably dispatch those asynchronous POST requests.
The client then retained the form busy state after the failed request, making the Settings interface
appear frozen.

## Corrections

- Added a dedicated authenticated and CSRF-protected `POST /admin/settings/action` route for every
  Settings mutation.
- Preserved `POST /admin/settings` as the no-JavaScript fallback.
- Replaced only the active Settings tab pane after a successful action; the page shell, navigation,
  and inactive tabs are not rebuilt.
- Only the clicked submit button is disabled while saving. Other tabs and controls remain usable.
- Added a bounded 45-second client timeout, safe button restoration, and inline failure feedback.
- Refreshed server alerts and CSRF values without a full page reload.
- Synchronized URL hash/query state and every hidden `return_tab` field.
- Preserved expanded accordion sections and the browser scroll position after a pane refresh.

## Master audit results

- Automated tests: **93 passed**
- Application statement coverage: **71%**
- Ruff lint: **PASS**
- Ruff formatting: **PASS**
- Python compilation: **PASS**
- Jinja template parse/compile: **PASS** (10 templates)
- Settings JavaScript syntax (`node --check`): **PASS**
- Dedicated Settings action route smoke test: **PASS**
- Original non-JavaScript Settings fallback: **PASS**
- PostgreSQL table DDL compilation: **PASS** (16 tables)
- Alembic PostgreSQL offline upgrade through head: **PASS**
- Python wheel and source distribution build: **PASS**
- Dependency integrity (`pip check`): **PASS**
- Secret-pattern and committed `.env` scan: **PASS**
- Baseline source files removed: **0**
- New database migration: **none**

One non-blocking Starlette TestClient deprecation warning is emitted by the test dependency. It is
not a production runtime failure.

## Remaining deployment-time checks

- Browser Settings actions through the live Coolify reverse proxy
- Keycloak administrator session continuity after redeployment
- JavaScript-disabled fallback on the production domain
- Runtime provider/API credentials against their real external services
