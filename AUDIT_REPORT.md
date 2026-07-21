# RegHub v0.2.3.2 Settings AJAX & Repository Endpoint Hotfix — Production Audit

## Baseline and zero-freedom compatibility

- Built directly from the live v0.2.3.1 API Settings & Logs Hotfix source archive.
- No existing endpoint, OIDC route, SQLAdmin view, feature flag, integration, encrypted credential,
  service token, block rule, operation history, template record, manifest, migration, Docker
  entrypoint, Coolify variable, or deployment boundary was removed.
- Existing database revision remains `20260721_0005`; this hotfix requires no migration.

## Forensic findings and corrections

### Settings actions and active-section continuity

The v0.2.3.1 server correctly understood `return_tab`, but most Settings actions still used normal
form navigation. The browser therefore reloaded the full page and client tab activation could race
against the newly rendered document. Every Settings mutation now uses one delegated asynchronous
form controller. It submits the exact clicked action, parses the authenticated server response, and
replaces only the Settings content shell. URL query/hash state, session storage, hidden return
fields, and server-rendered active classes provide layered fallback so the originating section is
preserved even when JavaScript is unavailable or a normal reload occurs.

### Canonical original repository API

Added `GET /api/v1/templates/{slug}/repository`. It returns the published template's canonical source
repository URL, provider adapter, default branch, external repository ID, and latest successful
source revision. The route is additive, uses the existing Catalog API feature switch and `catalog`
service-token permission, and appears in Settings → API Manage with the existing asynchronous Check
and Use controls.

### Administrator-facing UI cleanup

Import and Settings pages no longer display implementation commentary, credential-mode notices, or
instructions about internal operation mechanics. Functional availability warnings, validation
errors, success states, and security controls remain visible. Operation pages use the production
label “Operation logs”.

### Operation terminal readability

Completed operations open at their first log entry and running operations continue following the
latest entry. Start/Latest controls, log counts, formatted structured context, richer sync stages,
and compact forced row sizing provide a denser terminal view without removing persisted diagnostics.

## Automated verification

- Automated tests: **91 passed**
- Application statement coverage: **71%**
- Ruff lint: **PASS**
- Ruff formatting: **PASS**
- Python compilation: **PASS**
- Jinja template compilation: **PASS** (10 templates)
- Settings JavaScript syntax (`node --check`): **PASS**
- PostgreSQL table DDL compilation: **PASS** (16 tables)
- Alembic PostgreSQL offline upgrade through head: **PASS**
- Package wheel build: **PASS**
- Re-extracted release test suite: **PASS** (91 passed)
- Dependency integrity (`pip check`): **PASS**
- Baseline files removed: **0**
- New database migration: **none**

One non-blocking Starlette TestClient deprecation warning is emitted by the test dependency. It does
not represent a production runtime failure.

## Deployment-time verification still required

- Browser AJAX behavior through the live Coolify reverse proxy
- Settings fallback behavior with JavaScript disabled
- Keycloak administrator session continuity after redeployment
- Live service-token checks for the new repository endpoint
