# Changelog

## 0.2.3.2 - 2026-07-21

### Settings continuity and source endpoint hotfix

- Converted every Settings mutation to asynchronous in-page submission with immediate DOM refresh and no full-page navigation.
- Added server-rendered tab activation, explicit return targets, URL hash/query persistence, and a non-JavaScript fallback that remains on the originating section.
- Added `GET /api/v1/templates/{slug}/repository` for canonical repository URL, adapter, branch, external ID, and latest source revision.
- Registered the repository endpoint in Settings → API Manage for single-route checks and copy-ready usage instructions.
- Added operation-log Start/Latest navigation, structured JSON formatting, terminal log counts, compact forced row sizing, and richer sync diagnostics.
- Removed development-oriented helper banners from import and settings pages while preserving operational errors and disabled-state warnings.
- Added no database migration and removed no existing route, feature, setting, token, record, or deployment behavior.

## 0.2.3.1 - 2026-07-21

### Settings and API verification hotfix

- Preserved the active Settings tab after every runtime action, validation error, token change, integration update, and API policy update.
- Repaired in-application API verification to call the root FastAPI application instead of the mounted SQLAdmin sub-application.
- Added a dedicated API endpoint registry with per-route asynchronous Check and secure Use/copy instructions.
- Added checks for health, readiness, capabilities, catalog, resources, facets, change feed, manifest, assets, and freshness routes.
- Expanded import/sync operation diagnostics with redacted input context, source metadata, analyzer output, change sets, media counts, transaction details, elapsed time, exception stage, and bounded traceback.
- Rebuilt terminal log rows as compact single-row entries and removed the empty data grid row that caused excessive vertical spacing.
- Added no database migration and removed no existing endpoint, feature, setting, credential, operation, template, or deployment behavior.

## 0.2.3 - 2026-07-21

### Operations correctness and diagnostics

- Changed duplicate repository import from Failed to Skipped / No change while linking the existing template.
- Expanded import/sync diagnostics into compact terminal-style provider, analyzer, media, transaction, and exception logs.
- Added operation search, status/type/order filters, and safe clearing of terminal history.
- Added template/asset search to Asset Gallery and productive search/filter/sorting across registry administration tables.

### Runtime API management

- Added Development and token-protected Live API modes managed from Settings without redeployment.
- Added scoped `vt_reg_...` service tokens with one-time display, HMAC-SHA256 storage, expiry, last-used tracking, enable/disable, and deletion.
- Added runtime IP, CIDR, and hostname block rules with common private-network aliases.
- Added authenticated in-application API endpoint checks with HTTP status and timing.
- Added additive migration `20260721_0005_api_access_operations`; no existing data or API path was removed.

## 0.2.2.1 - 2026-07-21

- Fixed the SQLAdmin custom-page flex shrink regression that broke Settings, Operations, imports, Asset Gallery, and the custom dashboard layout.
- Added a shared responsive admin layout with a required full-width Bootstrap column, safe text wrapping, responsive tables, and mobile controls.
- Rebuilt Settings as compact tabs and accordions so integration credentials no longer create an extremely long unreadable page.
- Added operation-log JSON polling and an automatic SSE-to-polling fallback so progress and logs remain visible through proxies that interrupt live streams.
- Added explicit connection state, manual refresh, non-empty waiting state, robust log copy, and wrapped result output to the operation detail page.
- Added submit-state feedback and double-submit prevention to GitHub, GitLab/Bitbucket, and Local Import pages.
- No database migration, public API removal, feature removal, or runtime settings reset.

## 0.2.2 - 2026-07-21

### Operations and administrator experience

- Added persistent `admin_operations` and `operation_logs` records.
- Added live operation progress, SSE log streaming, copy/export, retry, cancel, and return links.
- Routed repository imports, local imports, source sync, publication changes, screenshot generation,
  and screenshot retry actions through the Operations Console.
- Preserved the originating administrator page instead of always redirecting to the main list.
- Added clear structured success, failure, and request-ID feedback.

### Runtime Settings

- Added database-backed feature ON/OFF controls and administrator task permissions.
- Added runtime GitHub, GitLab, Bitbucket, AI, screenshot, and custom API configuration.
- Added encrypted runtime credential storage with optional Coolify environment fallback.
- Added immediate in-process configuration reload without redeployment.
- Added runtime switches for the public API and individual catalog API groups.

### API and stability

- Fixed the PostgreSQL JSONB `tag` filter that returned HTTP 500.
- Added structured generic HTTP 500 responses with request IDs while retaining server-side traces.
- Added additive migration `20260721_0004_operations_runtime_settings`.
- Removed no existing endpoint, table, column, template record, status, manifest, or Keycloak route.

## 0.2.1 - 2026-07-21

### Stabilization

- Added owner-based Provider auto-creation for GitHub, GitLab, and Bitbucket imports.
- Added initial-import Sync History records and migration backfill for existing templates.
- Fixed Sync Source selection handling, failure recording, requester tracking, and change summaries.
- Preserved manual and screenshot-service assets during source synchronization.
- Added recursive media discovery and README image detection across supported providers.
- Added a manual Asset Gallery with safe add, edit, delete, ordering, and thumbnail controls.
- Added tracked screenshot jobs with success/failure status, retry actions, and baseline public-HTTPS URL controls.
- Added assets, freshness, change-feed, and facets endpoints.
- Added tag/language/difficulty/use-case/quality/freshness filters and sorting.
- Added ETag and Last-Modified support for template detail and manifest endpoints.
- Preserved every v0.2.0 endpoint, database record, Keycloak route, status, manifest, and deployment boundary.

### Database

- Added additive migration `20260721_0003_provider_media_stabilization`.
- Added sync audit fields and `screenshot_jobs`; no existing object is removed or renamed.

## 0.2.0 - 2026-07-21

### Fixed

- Removed the faulty GitHub URL HTML pattern that blocked valid repository imports in browsers.
- Retained the SQLAdmin 0.29 Template list/filter compatibility fix from v0.1.1.
- Added readable provider authentication, not-found, and rate-limit errors.

### Smart Registry

- Added bounded repository analysis without cloning, installing, building, or executing source code.
- Added framework/version detection for Astro, Next.js, React + Vite, React, Vue, Nuxt,
  SvelteKit, Laravel, Django, FastAPI, Static HTML, and Docker.
- Added language, package-manager, build/start-command, environment-variable, screenshot,
  difficulty, use-case, and category detection.
- Added deterministic metadata generation with optional OpenAI-compatible enrichment.
- Added a transparent 0–100 quality score with a stored score breakdown.
- Added source synchronization while preserving curated identity, classification, featured flag,
  and Draft/Published/Disabled status.
- Added version snapshots, sync history, and template asset records.
- Added backwards-compatible Manifest v2 while retaining Manifest v1 validation.
- Added GitLab and Bitbucket public/private metadata adapters.
- Added disabled-by-default local JSON manifest and safely inspected ZIP import.
- Added optional isolated screenshot-service integration.
- Added `/api/v1/capabilities` and enriched public template response fields.

### Database

- Added additive Alembic migration `20260720_0002_smart_registry`.
- No existing table, column, template, API path, OIDC setting, or publication status is removed.

## 0.1.1 - 2026-07-20

- Fixed `/admin/template/list` returning HTTP 500 with SQLAdmin 0.29.
- Added GitHub PAT status/errors and bounded Astro package detection.

## 0.1.0 - 2026-07-20

- Initial RegHub registry-only MVP foundation.
