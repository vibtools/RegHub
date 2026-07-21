# RegHub

Current release: **v0.2.2.1 UI & Operations Hotfix**

RegHub is the registry service for the YGIT ecosystem. It imports and analyzes template metadata,
manages publication, and serves a stable read-only API to `ygit.net`. RegHub does **not** build or
deploy user projects.

## Fixed service boundaries

- Identity: `auth.vib.tools` / Keycloak
- Registry: `reghub.ygit.dev`
- Deployment: `ygit.net`
- Repository sources: GitHub, GitLab, Bitbucket, local manifest/ZIP
- Hosting: Coolify

## v0.2.2 features

All v0.2.1 registry, provider, media, API, Keycloak, and database behavior is preserved.

- Fixed PostgreSQL JSONB tag filtering (`?tag=astro`).
- Added persistent administrator operations with status, progress, logs, result, and errors.
- Added a Coolify-style Operations Console with live SSE logs, copy, TXT export, retry, cancel,
  and context-preserving return links.
- GitHub/GitLab/Bitbucket/local imports, source sync, publication actions, thumbnail generation,
  and screenshot retries now open an operation progress page instead of silently returning to a
  list page.
- Added runtime Settings for project feature ON/OFF controls and administrator task permissions.
- Added runtime GitHub, GitLab, Bitbucket, AI, screenshot, and custom third-party API configuration.
- Runtime credentials are encrypted before database storage and never rendered back to the UI.
- Runtime settings are applied immediately without a Coolify redeploy. Existing environment values
  remain optional bootstrap/fallback values.
- Added runtime control for the RegHub public API and its catalog, assets, freshness, facets, and
  change-feed sections. Health, readiness, authentication, and Settings remain available.
- Added structured expected/unexpected API errors with request IDs.

## Operations Console

```text
/admin/operations
```

Long-running administrator tasks use persistent states:

```text
queued -> running -> succeeded | failed | cancelled
```

A running operation displays progress and debug logs. Logs remain available after completion and
can be copied or exported. Queued operations left before execution are recovered after startup. An operation interrupted while
running is marked failed and can be inspected and retried.

## Runtime Settings

```text
/admin/settings
```

The Settings page manages:

- Feature ON/OFF state
- Administrator task ALLOW/BLOCK permission
- Public API feature switches
- GitHub/GitLab/Bitbucket credentials and state
- AI and screenshot integration state
- Custom third-party API configurations
- Environment fallback behavior

Runtime secrets are encrypted with a key derived from `SESSION_SECRET`. Keep `SESSION_SECRET`
unchanged across deployments or previously stored runtime credentials cannot be decrypted.

## Security model

RegHub reads bounded metadata through provider APIs. It does not clone repositories, install
packages, run builds, start templates, or execute uploaded code. Screenshot capture remains delegated
to an isolated external service. Preview, screenshot, and runtime integration URLs must pass the
existing public-HTTPS security boundary. OIDC administrator authentication and CSRF protection remain
mandatory for administrator actions and Settings.

## Public API

Existing paths and response contracts remain compatible. Published templates are exposed only.

```text
GET /api/v1/templates
GET /api/v1/templates/{slug}
GET /api/v1/templates/{slug}/manifest
GET /api/v1/templates/{slug}/assets
GET /api/v1/templates/{slug}/freshness
GET /api/v1/templates/changes
GET /api/v1/facets
GET /api/v1/categories
GET /api/v1/providers
GET /api/v1/frameworks
GET /api/v1/capabilities
GET /api/v1/health
GET /api/v1/ready
```

## Upgrade

1. Take a PostgreSQL backup.
2. Replace project files while preserving `.git` and any local `.env`.
3. Commit and push to `main`.
4. Redeploy in Coolify.
5. The entrypoint runs `alembic upgrade head` and `python -m scripts.seed` automatically.
6. Verify health, readiness, tag filtering, Operations, and Settings.

See `docs/17_V0.2.2_UPGRADE.md` and `docs/18_V0.2.2_OPERATIONS_SETTINGS.md`.
