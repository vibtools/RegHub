# Changelog

## v0.3.1.0 — Architecture Stabilization Release

### Security

- Rejected roleless legacy/malformed administrator cookies instead of inferring Super Admin access.
- Added purpose-bound cryptographic key derivation for OIDC state, administrator authentication, and
  the SQLAdmin auxiliary session without adding deployment configuration.
- Completed local logout by clearing all RegHub authentication cookies and delegating to the existing
  OIDC end-session endpoint when configured.
- Prevented private GitHub, GitLab, and Bitbucket repository content from reaching optional AI
  metadata enrichment.

### Registry architecture

- Retained framework, language, package-manager, license, topic, README, repository, media, quality,
  and security analysis inside RegHub.
- Removed generated build/start/runtime/environment/deployment recommendations and the
  deployment-readiness quality dimension.
- Kept Manifest v1/v2 schemas and all `/api/v1` paths compatible; generated manifests are now
  deployment-neutral because YGIT owns deployment decisions.

### Database and repository integrity

- Added migration `20260722_0007_architecture_stabilization`.
- Aligned `templates.external_repository_id` with the existing 160-character model contract.
- Normalized invalid numeric values, removed exact duplicate asset rows, and added bounded checks and
  an exact asset identity constraint.
- Removed redundant unique indexes where an equivalent unique constraint already exists.
- Cleaned obsolete generated deployment intelligence from current analysis, version snapshots, import
  snapshots, and stored manifests.
- Removed historical generated compatibility, inventory, and verification reports from the source
  tree while preserving release manifests and substantive documentation.

### Compatibility

- Added no feature, endpoint, integration, provider, admin page, setting, service, or deployment step.
- Kept the current Dockerfile, GitHub Actions workflow, Coolify process, Keycloak roles, Settings,
  Operations, Governance, API access, and template lifecycle unchanged.
- Existing administrators are required to authenticate once after deployment because legacy cookies
  are intentionally invalidated.

## v0.3.0.3 — CI Compatibility and Resilience Hotfix

- Updated historical admin tests to use the production `AdminIdentity` RBAC contract without weakening runtime authorization.
- Made catalog caching fail-open when the cache service is absent or temporarily unavailable.
- Isolated terminal audit/cache side effects so they cannot rewrite a completed operation into a false failure.
- Added regression tests for cache and audit degradation paths.
- Added bounded retry wrappers for transient package/network/process failures in CI and a read-only Windows PowerShell validation script.
- Kept the 70% coverage gate, existing APIs, migrations, Settings, Governance, worker controls, data, and deployment boundaries unchanged.

## v0.3.0.2 — CI Quality Gate Hotfix

- Corrected Ruff import ordering and removed unused imports introduced by v0.3.0/v0.3.0.1.
- Corrected test-only lint directives without changing runtime behavior.
- No database migration, API contract, Settings, Governance, worker, or deployment behavior changed.

## 0.3.0.1 - 2026-07-22

- Fixed the Governance custom page layout by using the shared responsive SQLAdmin content block.
- Added responsive governance posture tiles, bounded infrastructure/authorization cards, and readable
  audit-chain status.
- Added a runtime **Redis Operation Worker** feature switch under Project feature control.
- Added safe activation checks for `REDIS_URL`, Redis connectivity, and standalone-worker heartbeat.
- Kept OFF mode on the in-process runner and made disabled workers drain already queued durable jobs.
- Updated readiness and capabilities to report the effective operation backend.
- Added no migration and removed no existing feature, route, record, token, role, or deployment behavior.

## 0.3.0 - 2026-07-21

### Production infrastructure

- Added an opt-in Redis operation queue and standalone worker while preserving the in-process default.
- Added queue de-duplication, distributed operation locks, heartbeat, reconciliation, cancellation
  checks and restart-safe queued-operation recovery.
- Added Redis/in-memory catalog caching with shared generation invalidation and fail-open memory
  degradation.
- Added Redis/in-memory rate limits for public IPs, service tokens, authenticated-token IP ceilings
  and administrator sessions.
- Added trusted-proxy forwarding normalization and disabled unconditional Uvicorn proxy-header trust.
- Added readiness details for worker, cache and rate-limit infrastructure.

### Governance and security

- Added Keycloak-backed Viewer, Editor, Publisher, Security Admin and Super Admin roles.
- Preserved legacy `reghub-admin` and legacy signed-cookie Super Admin behavior.
- Added permission checks for mutations, imports, sync, media, publication, Settings, API security,
  operation retry/cancel and operation-history administration.
- Added immutable HMAC hash-chained audit events, nested secret redaction, signing-key IDs and chain
  verification.
- Added a Governance dashboard and read-only Audit Trail.
- Added versioned runtime encryption and audit-signing keyrings with v0.2.x secret compatibility and
  previous-key rotation support.

### Database and delivery

- Added operation requester roles and audit-chain tables through additive migration `20260721_0006`.
- Added JSONB GIN and catalog ordering indexes.
- Added PostgreSQL/Redis CI, Alembic and seed checks, coverage floor, dependency audit and Docker
  startup smoke testing.
- Removed no existing API route, response field, database object, template record, runtime setting,
  Keycloak route or Coolify boundary.

## 0.2.3.4 - 2026-07-21

### Import completion experience

- Added a context-aware View Template action beside the live progress refresh control.
- Added a production template result card with thumbnail, title, short description, provider, category, framework, slug, quality score, status, repository, and details links.
- Added live status payload enrichment so the template card appears without reloading after import completion.
- Kept duplicate imports as Skipped / no-change and replaced failure-style messaging with a clear Already found state.
- Added Continue to update template, which queues a single-template source synchronization while preserving curated registry fields.
- Added no database migration and removed no existing API, Settings control, operation, template record, Keycloak route, or deployment behavior.

## 0.2.3.3 - 2026-07-21

- Added a dedicated Settings AJAX mutation endpoint to eliminate production HTTP 404 responses.
- Preserved the original Settings POST route as a no-JavaScript fallback.
- Replaced only the active Settings pane after mutations instead of replacing the full page shell.
- Kept tabs responsive while a form is saving and added timeout recovery.
- Synchronized active-tab state, return targets, CSRF values, and inline server feedback.

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
