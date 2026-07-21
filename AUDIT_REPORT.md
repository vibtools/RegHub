# RegHub v0.2.2.1 UI & Operations Hotfix — Forensic Audit

## Baseline

The audit used the uploaded v0.2.2 replace-ready project as the immutable baseline. No existing
feature, model, API path, OIDC route, migration, integration record, template record, or operation
history behavior was removed.

## Confirmed root cause

SQLAdmin's `sqladmin/layout.html` already places `{% block content %}` inside:

```html
<div class="row row-deck row-cards">...</div>
```

The v0.2.2 custom templates inserted several top-level elements directly inside that Bootstrap row.
Those elements were not `.col-*` children, so Bootstrap treated each page section as an independent
flex item. On common desktop and smaller widths this produced narrow vertical strips, unbounded page
length, squeezed forms, unreadable API configuration controls, and apparently blank operation/log
areas.

Affected custom pages:

- Settings
- Operations list
- Operation detail and live logs
- GitHub import
- GitLab / Bitbucket import
- Local manifest / ZIP import
- Asset Gallery
- Custom SQLAdmin dashboard

## Hotfix applied

- Added one shared `reghub_layout.html` that always supplies a full-width `col-12` child inside the
  SQLAdmin row.
- Added bounded responsive page, table, form, code, JSON, and log-panel rules.
- Rebuilt Settings into three tabs: Feature controls, Integrations, and Add custom API.
- Changed feature groups and integration editors to accordions so only the selected editor expands.
- Preserved every settings field, ON/OFF control, ALLOW/BLOCK permission, credential action,
  fallback option, and custom API action.
- Added visible import submit state and duplicate-submit prevention.
- Added `/admin/operations/{id}/logs.json` for authenticated incremental log retrieval.
- Added automatic SSE-to-polling fallback, connection state, manual refresh, waiting state, robust
  copy behavior, and bounded result JSON on operation details.
- Normalized Asset Gallery and dashboard layout without removing their functions.

## Operations reliability findings

The persistent operation runner and database logs were present in v0.2.2. The primary blank-page
symptom was layout collapse. A second resilience gap existed: the browser depended only on SSE for
new logs. Reverse proxies or browsers that interrupted the stream had no alternate transport. The
hotfix keeps SSE as the primary transport and automatically switches to JSON polling every 1.5
seconds after repeated stream errors.

Server-rendered logs remain visible before JavaScript connects, so a live transport problem no
longer produces a blank log page.

## Database and deployment impact

- New migration: **none**
- Current Alembic head remains `20260721_0004_operations_runtime_settings`
- Existing runtime settings and encrypted credentials remain unchanged
- Coolify environment changes: **none required**
- Keycloak changes: **none required**

## Automated verification

- Automated tests: **80 passed**
- Application statement coverage: **68%**
- Ruff lint: **PASS**
- Ruff formatting: **PASS**
- Python compilation: **PASS**
- Jinja compilation for all custom administrator templates: **PASS**
- Operations JSON log route: **PASS**
- Server-rendered initial logs: **PASS**
- SSE polling fallback markup/regression tests: **PASS**
- PostgreSQL Alembic offline SQL through existing head: **PASS**
- Wheel and source distribution build: **PASS**
- Dependency integrity: **PASS**
- Baseline files removed: **0**

One non-blocking Starlette TestClient deprecation warning remains in the test dependency and is not a
production runtime error.

## Live verification required

After Coolify redeploy, verify Settings at desktop and mobile width, start one GitHub import, and
confirm the operation page shows either `Live stream` or `Polling fallback` while logs and progress
continue to update.
