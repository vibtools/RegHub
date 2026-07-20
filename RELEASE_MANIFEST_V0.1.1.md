# RegHub v0.1.1 Release Manifest

## Production behavior preserved

- Keycloak/OIDC login and signed admin session
- SQLAdmin CRUD and lifecycle actions
- PostgreSQL models and existing Alembic migration
- Public `/api/v1` routes and response schemas
- Template manifest schema 1.0
- GitHub API metadata import without cloning
- Coolify Dockerfile, entrypoint, health, and readiness behavior

## Changed runtime files

- `app/admin/views.py`
- `app/container.py`
- `app/integrations/github/client.py`
- `app/main.py`
- `app/registry/adapters/base.py`
- `app/registry/adapters/github.py`
- `app/registry/framework.py`
- `templates/github_import.html`

## Added regression coverage

- `tests/test_admin_template_list.py`
- `tests/test_astro_import.py`
- `tests/test_github_client.py`
- Expanded `tests/test_framework_detection.py`

## Database impact

None. No migration file was added, changed, removed, or reordered.
