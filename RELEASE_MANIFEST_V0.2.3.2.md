# RegHub v0.2.3.2 Release Manifest

## Baseline

- Built directly from the live v0.2.3.1 API Settings & Logs Hotfix.
- Preserves all public API routes, SQLAdmin pages, templates, providers, assets, operations, service tokens, block rules, runtime integration secrets, Keycloak routes, Coolify variables, and database records.
- No database migration is required.

## Hotfix scope

- Asynchronous Settings actions with in-place UI refresh.
- Active Settings tab preserved across AJAX updates, validation errors, and normal reload fallback.
- Canonical original repository endpoint: `GET /api/v1/templates/{slug}/repository`.
- Repository endpoint included in API Manage Check/Use registry.
- Compact full operation-log view with Start/Latest navigation and richer sync diagnostics.
- Production UI cleanup of development-oriented import/settings commentary.

## Compatibility

- Existing API contracts remain unchanged; the repository endpoint is additive.
- Existing service tokens continue to use the `catalog` permission for the new repository endpoint.
- Existing migrations remain unchanged through `20260721_0005_api_access_operations`.
