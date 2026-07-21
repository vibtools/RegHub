# RegHub

Current release: **v0.2.0 Smart Registry**

RegHub is the registry service for the YGIT ecosystem. It imports and analyzes template
metadata, manages publication, and serves a stable read-only API to `ygit.net`. RegHub does
**not** build or deploy user projects.

## Fixed service boundaries

- Identity: `auth.vib.tools` / Keycloak
- Registry: `reghub.ygit.dev`
- Deployment: `ygit.net`
- Repository sources: GitHub, GitLab, Bitbucket, local manifest/ZIP
- Hosting: Coolify

## v0.2 features

- OIDC-protected SQLAdmin panel
- GitHub, GitLab, and Bitbucket metadata import without repository cloning
- Local manifest and bounded ZIP inspection, disabled by default
- Auto framework/version, language, package-manager, build command, and environment detection
- Auto title, description, tags, category, difficulty, and use-case metadata
- Optional OpenAI-compatible metadata enrichment
- Repository screenshot discovery and optional isolated screenshot-service generation
- Transparent quality score and breakdown
- Draft, Published, and Disabled lifecycle
- Source synchronization with version and sync history
- Backward-compatible Manifest v1 and enhanced Manifest v2
- Public read-only API for YGIT

## Security model

RegHub only reads bounded text metadata through provider APIs or inspects ZIP entries in memory.
It does not clone repositories, install packages, run builds, start templates, or execute uploaded
code. ZIP traversal, symlinks, encryption, entry count, compressed size, and uncompressed size are
validated. Local ZIP templates remain drafts until they have a deployable HTTPS repository.

## Public API

```text
GET /api/v1/templates
GET /api/v1/templates/{slug}
GET /api/v1/templates/{slug}/manifest
GET /api/v1/categories
GET /api/v1/providers
GET /api/v1/frameworks
GET /api/v1/capabilities
GET /api/v1/health
GET /api/v1/ready
```

Only Published templates are exposed.

## Local setup

```bash
cp .env.local.example .env
docker compose -f compose.local.yml up --build
```

## Coolify upgrade

1. Take a PostgreSQL backup.
2. Replace the project files, preserving `.git` and any local `.env`.
3. Commit and push to `main`.
4. Redeploy in Coolify.
5. The entrypoint runs `alembic upgrade head` and `python -m scripts.seed` automatically.
6. Verify `/api/v1/health`, `/api/v1/ready`, `/api/v1/capabilities`, admin imports, and sync.

See `docs/13_V0.2.0_UPGRADE.md` and `docs/14_V0.2.0_ENVIRONMENT.md`.
