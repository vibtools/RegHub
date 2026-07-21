# RegHub v0.2.2 Release Manifest

## Baseline

- Built from the live v0.2.1 Stabilization release.
- Existing template IDs, slugs, publication states, API paths, OIDC settings, and database data are
  preserved.
- No Smart Registry detection or manifest behavior was removed.

## Additive files and schema

- `app/operations/` — persistent operation service and runner
- `app/runtime/` — runtime feature and integration settings
- `app/models/admin_operation.py`
- `app/models/feature_flag.py`
- `app/models/integration_config.py`
- `templates/operations_list.html`
- `templates/operation_detail.html`
- `templates/settings.html`
- `migrations/versions/20260721_0004_operations_runtime_settings.py`

## Release scope

- Operations Console and live logs
- Context-preserving administrator actions
- Runtime Settings and encrypted credentials
- Public API feature control
- PostgreSQL tag-filter repair
- Structured API errors

## Deployment

The release is replace-ready. Preserve `.git`, `.env`, Coolify variables, PostgreSQL, Keycloak, and
all existing domains. Run the normal Coolify redeploy; the entrypoint applies the additive migration.
