# Changelog

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
