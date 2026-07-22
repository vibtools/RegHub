# RegHub

Current release: **v0.3.0.3 CI Compatibility and Resilience Hotfix**

RegHub is the registry service for the YGIT ecosystem. It imports and analyzes template metadata,
manages publication, and serves a stable read-only API to `ygit.net`. RegHub does **not** build or
deploy user projects.

## Fixed service boundaries

- Identity: `auth.vib.tools` / Keycloak
- Registry: `reghub.ygit.dev`
- Deployment: `ygit.net`
- Repository sources: GitHub, GitLab, Bitbucket, local manifest/ZIP
- Hosting: Coolify

## v0.3.0.1 governance and worker-control hotfix

All v0.3.0 APIs, RBAC, audit records, Settings, Operations, templates, migrations, and deployment
boundaries remain compatible.

- Repaired `/admin/governance` by rendering it through the shared full-width responsive admin block.
- Rebuilt governance posture into responsive status tiles, bounded cards, wrapped proxy/key values,
  and a readable audit summary.
- Added **Redis Operation Worker** to Settings → Project feature control.
- OFF keeps new operations in the existing in-process runner. ON routes new operations to Redis only
  after Redis connectivity and a healthy standalone-worker heartbeat are verified.
- Disabling the switch drains already queued Redis operations so administrator actions are not stranded.
- No database migration or existing route removal is required.

## v0.3.0 production infrastructure and governance

All v0.2.3.4 registry, import, Settings, Operations, API access, Keycloak, template and database
behavior remains compatible.

- Added optional Redis-backed durable operations with a standalone worker. The default remains
  `inprocess`, so the current Coolify service can be upgraded without Redis.
- Added Redis/in-memory catalog cache, generation invalidation and runtime failover.
- Added trusted-proxy normalization and per-IP, per-token and administrator rate limiting.
- Added Keycloak RBAC for Viewer, Editor, Publisher, Security Admin and Super Admin while preserving
  legacy `reghub-admin` access.
- Added a read-only, HMAC-signed hash-chain audit trail and `/admin/governance` posture dashboard.
- Added versioned runtime/audit keyrings with v0.2.x secret-decryption compatibility.
- Added PostgreSQL/Redis integration CI, migration/seed validation, dependency audit and Docker smoke.
- Added additive migration `20260721_0006_production_governance`; no existing route, field, record or
  deployment boundary was removed.

## v0.2.3.4 hotfix

All v0.2.3.3 Settings, Operations, API access, registry, Keycloak, and database behavior is preserved.

- Added a View Template action beside live progress after a successful import or single-template sync.
- Rebuilt the operation-side panel as a responsive template result card with thumbnail, title, description, provider, category, framework, slug, quality, status, and source links.
- Duplicate repository imports now finish as **Already found / Skipped**, never as a failure.
- Added **Continue to update template**, which starts the existing source-sync workflow and preserves curated fields.
- Added no database migration and removed no existing route, feature, setting, token, record, or operation history.

## v0.2.3.3 hotfix

All v0.2.3.2 registry, API access, operation, settings, Keycloak, and database behavior is preserved.

- Added a dedicated Settings mutation route for asynchronous actions.
- Settings now refreshes only the active tab pane instead of replacing the full page shell.
- Only the clicked action button enters a busy state; other tabs and controls stay responsive.
- Added request timeout recovery, inline feedback, CSRF refresh, and current-tab preservation.
- The original Settings POST route remains available as the non-JavaScript fallback.
- No database migration is required.

## v0.2.3.1 hotfix

All v0.2.2.1 registry, provider, media, API, Keycloak, runtime-settings, and database behavior is preserved.

- Settings actions remain on the active Feature, Integration, API Manage, or Custom API tab.
- API Manage verifies the root FastAPI routes and supports per-endpoint Check and Use/copy controls.
- Operation terminal logs include compact, redacted developer diagnostics and bounded failure tracebacks.

- Duplicate imports finish as **Skipped / No change** and link the existing template.
- Import and sync operations show compact developer-oriented terminal diagnostics.
- Operations Console supports search, filtering, ordering, and safe terminal-history clearing.
- Asset Gallery supports template search and asset filtering.
- Registry administration tables include productive search, filters, and date/name sorting.
- Settings includes **API Manage** with Development/Live mode, scoped service tokens, client block rules, and endpoint checks.
- Raw `vt_reg_...` service tokens are shown once and only keyed digests are stored.
- Live Mode protects registry data endpoints while health and readiness remain public.

## Operations Console

```text
/admin/operations
```

Long-running administrator tasks use persistent states:

```text
queued -> running -> succeeded | skipped | failed | cancelled
```

A running operation displays progress and detailed operation logs. Logs remain available after completion and
can be copied or exported. Queued operations left before execution are recovered after startup. An operation interrupted while
running is marked failed and can be inspected and retried.

## Runtime Settings

```text
/admin/settings
```

The Settings page manages:

- Feature ON/OFF state
- Administrator task ALLOW/BLOCK permission
- Public API feature switches
- GitHub/GitLab/Bitbucket credentials and state
- AI and screenshot integration state
- Custom third-party API configurations
- Environment fallback behavior
- Development/Live API mode
- Scoped service tokens and IP/CIDR/hostname block rules
- Live API endpoint checks

Runtime secrets use a versioned encryption keyring. Existing v0.2.x credentials remain readable
through the unchanged `SESSION_SECRET`; production should add an independent
`RUNTIME_ENCRYPTION_KEY` and retain previous keys during rotation.

## Security model

RegHub reads bounded metadata through provider APIs. It does not clone repositories, install
packages, run builds, start templates, or execute uploaded code. Screenshot capture remains delegated
to an isolated external service. Preview, screenshot, and runtime integration URLs must pass the
existing public-HTTPS security boundary. OIDC administrator authentication and CSRF protection remain
mandatory for administrator actions and Settings.

## Public API

Existing paths and response contracts remain compatible. Published templates are exposed only.

```text
GET /api/v1/templates
GET /api/v1/templates/{slug}
GET /api/v1/templates/{slug}/manifest
GET /api/v1/templates/{slug}/repository
GET /api/v1/templates/{slug}/assets
GET /api/v1/templates/{slug}/freshness
GET /api/v1/templates/changes
GET /api/v1/facets
GET /api/v1/categories
GET /api/v1/providers
GET /api/v1/frameworks
GET /api/v1/capabilities
GET /api/v1/health
GET /api/v1/ready
```

## Upgrade

1. Take a PostgreSQL backup.
2. Replace project files while preserving `.git` and any local `.env`.
3. Commit and push to `main`.
4. Redeploy in Coolify.
5. The entrypoint runs `alembic upgrade head` and `python -m scripts.seed` automatically.
6. Verify health, readiness, tag filtering, Operations, and Settings.

See `docs/31_V0.3.0_PRODUCTION_INFRASTRUCTURE_GOVERNANCE.md`,
`docs/32_V0.3.0_UPGRADE.md`, `docs/33_V0.3.0_RBAC_AUDIT.md`,
`docs/37_V0.3.0.3_CI_COMPATIBILITY_RESILIENCE_HOTFIX.md` and
`docs/38_V0.3.0.3_UPGRADE.md`.
