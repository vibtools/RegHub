# RegHub v0.2.3.3 Release Manifest

## Baseline

- Built from the live v0.2.3.2 Settings AJAX and Repository Endpoint hotfix.
- No existing API route, administrator page, feature flag, integration, template record, service token,
  block rule, operation history, migration, Keycloak setting, or Coolify setting was removed.
- Database schema is unchanged.

## Hotfix scope

- Added a dedicated `POST /admin/settings/action` mutation route while preserving the original
  `POST /admin/settings` no-JavaScript fallback.
- Settings AJAX now replaces only the active tab pane instead of the entire Settings page shell.
- Only the submitted button enters a busy state; the page and other tabs remain responsive.
- Added a 45-second client timeout with safe recovery and clear inline feedback.
- Active tab and all `return_tab` fields stay synchronized for AJAX and fallback submissions.
- Server success/error alerts and CSRF values refresh without a full page reload.

## Compatibility

- No migration is required.
- Existing runtime credentials and service tokens remain valid.
- Existing public API and administrator URLs remain unchanged.
