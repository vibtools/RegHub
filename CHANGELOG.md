# Changelog

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
