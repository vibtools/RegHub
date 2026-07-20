# Changelog

## 0.1.1 - 2026-07-20

### Fixed

- Fixed `/admin/template/list` returning HTTP 500 with SQLAdmin 0.29.
- Replaced unsupported raw SQLAlchemy `column_filters` entries with SQLAdmin filter objects.
- Preserved Status, Featured, and Framework filtering in the Templates admin page.

### Improved

- Added explicit authenticated/unauthenticated GitHub API status to the import page.
- Added clear bad-token and GitHub rate-limit error messages without exposing secrets.
- Added bounded root `package.json` metadata reading through the GitHub Contents API.
- Expanded Astro detection through GitHub topics, Astro config files, and package dependencies.
- Import success messages now show the detected framework.
- Added regression tests for the SQLAdmin list page, GitHub PAT wiring, and Astro detection.

### Compatibility

- No database schema change.
- No Alembic migration required beyond the existing migration.
- No API endpoint removed or renamed.
- No Keycloak/OIDC, Coolify, domain, manifest v1, or deployment boundary change.

## 0.1.0 - 2026-07-20

- Initial RegHub registry-only MVP foundation.
- OIDC SQLAdmin access, GitHub metadata import, Registry SDK, public API, migrations and Coolify deployment.
