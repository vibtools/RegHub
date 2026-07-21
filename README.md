# RegHub

Current release: **v0.2.3.4 Import Experience Hotfix**

RegHub is the registry service for the YGIT ecosystem. It imports and analyzes template metadata,
manages publication, and serves a stable read-only API to `ygit.net`. RegHub does **not** build or
deploy user projects.

## Fixed service boundaries

- Identity: `auth.vib.tools` / Keycloak
- Registry: `reghub.ygit.dev`
- Deployment: `ygit.net`
- Repository sources: GitHub, GitLab, Bitbucket, local manifest/ZIP
- Hosting: Coolify

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

Runtime secrets are encrypted with a key derived from `SESSION_SECRET`. Keep `SESSION_SECRET`
unchanged across deployments or previously stored runtime credentials cannot be decrypted.

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

See `docs/29_V0.2.3.4_IMPORT_EXPERIENCE_HOTFIX.md` and `docs/30_V0.2.3.4_UPGRADE.md`.
