# RegHub v0.2.2.1 UI & Operations Hotfix

## Baseline

- Built directly from the deployed v0.2.2 Operations Console & Runtime Settings release.
- Preserves all v0.2.2 feature flags, integration records, encrypted secrets, operation history,
  template data, API paths, OIDC settings, and Coolify configuration.
- No schema migration is required.

## Root cause repaired

SQLAdmin places custom page content inside a Bootstrap `.row`. The v0.2.2 custom templates rendered
multiple top-level elements directly inside that row instead of inside a full-width `.col-*` child.
Bootstrap therefore treated every section as a flex item, allowing content to shrink into narrow
columns or extend into extremely long layouts. Settings and operation log pages were most affected.

## Hotfix scope

- Shared `templates/reghub_layout.html` full-width wrapper for every custom administrator page.
- Responsive wrapping, table overflow handling, mobile controls, and bounded log/JSON panels.
- Compact Settings tabs and accordions; only one integration editor is expanded at a time.
- SSE live operation logs with automatic JSON polling fallback.
- New authenticated operation logs JSON route for resilient live updates.
- Import submit indicators and duplicate-submit prevention.
- Asset Gallery and custom dashboard layout normalization.

## Compatibility

No existing feature, API, model, table, migration, route, integration, or administrator action was
removed. This release is a replace-ready UI and operations reliability patch.
