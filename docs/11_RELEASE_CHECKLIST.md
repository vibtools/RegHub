# Release Checklist

- Tests and Ruff pass
- Alembic upgrades an empty PostgreSQL database
- Seed is idempotent
- OIDC callback and admin claim are verified
- Draft/disabled templates never appear publicly
- GitHub import rejects malformed/private/archived repositories
- No secrets exist in repository history
- Coolify health, HTTPS, logs, and backups are confirmed

## v0.2.1 stabilization checks

- Provider is auto-created from GitHub/GitLab/Bitbucket owner metadata.
- Existing templates without sync history receive a backfill record.
- New import creates an `initial_import` sync row.
- Manual Sync Source creates a success/failure row with requester and changes.
- Manual and screenshot-service assets survive source sync.
- Asset Gallery add/edit/delete works with public HTTPS URLs.
- Screenshot Jobs records success/failure without exposing tokens.
- Assets, freshness, changes, facets, filters, sorting, ETag, and 304 are verified.

## v0.2.2 operations and settings checks

- `?tag=astro` returns HTTP 200 on PostgreSQL.
- Operations and Settings pages render behind administrator authentication.
- Sync/import/publication/media actions open an operation detail page.
- Live logs, copy/export, retry/cancel, and return links work.
- Runtime feature and integration updates apply without redeploy.
- Runtime secrets are encrypted and never rendered.
- Public API feature OFF returns structured HTTP 503 while health/readiness remain available.

## v0.2.3 operations and API-access checks

- Duplicate repository import completes as Skipped / No change and links the existing template.
- Import History records the duplicate request as succeeded with `outcome=already_exists`.
- Import/sync operation logs include adapter, metadata, analyzer, resource, transaction, and safe
  exception details without credentials.
- Operations search/filter/order and terminal-history clearing work; queued/running records survive.
- Asset Gallery template search and asset filters work with large catalogs.
- Template and registry administration tables sort and filter without SQLAdmin errors.
- A service token is shown once and only its keyed digest is stored.
- Live Mode rejects unauthenticated registry requests and accepts permitted token scopes.
- Development Mode remains publicly readable while block rules still apply.
- IP/CIDR/hostname block rules can be added, edited, disabled, and deleted.
- API endpoint check reports health, readiness, catalog, capabilities, and resource status.
- Health/readiness and administrator recovery surfaces remain reachable.

## v0.3.0 infrastructure and governance checks

- Legacy `reghub-admin` still receives Super Admin access.
- Viewer/Editor/Publisher/Security Admin permissions match the documented matrix.
- Retry cannot replay an operation without its original task permission.
- Audit chain verifies and detects a modified event; sensitive nested details are redacted.
- In-process operation mode works without Redis.
- Redis worker mode preserves queued work and reports heartbeat/readiness.
- Cache invalidates after import, sync, publication and media changes.
- Redis cache/rate-limit runtime failure degrades safely to memory.
- Untrusted peers cannot spoof forwarding headers; configured proxy chains resolve the client IP.
- API rate limits return structured 429 and standard/legacy headers.
- Existing v0.2.x runtime secrets decrypt after upgrade.
- Alembic upgrades a v0.2.3.4 database without destructive DDL.
- GitHub CI PostgreSQL/Redis, dependency audit and Docker smoke gates pass.


## v0.3.1.0 architecture stabilization checks

- No public route, Settings control, admin page, provider, integration, service or workflow is added.
- Legacy/versionless roleless administrator cookies are rejected; current OIDC login issues v2 cookies.
- OIDC state, administrator cookie and SQLAdmin auxiliary session use distinct derived keys.
- Logout expires all local authentication cookies and cannot accept an untrusted return target.
- Private repositories never instantiate or call the AI metadata HTTP transport.
- Analysis retains registry metadata and contains no generated deployment recommendation fields.
- Generated manifests are deployment-neutral while v1/v2 parsing remains compatible.
- Migration upgrades the current schema, preserves IDs/status/history, cleans exact duplicate assets,
  aligns constraints and removes only redundant indexes/generated intelligence.
- Historical generated report noise, caches, build and distribution directories are absent.
- Existing GitHub Actions, Docker, entrypoint, seed and Coolify deployment behavior are unchanged.

## v0.3.2.0 production-readiness checks

- Version identity is `0.3.2.0` in package metadata and runtime/API responses.
- Hidden delivery files are present: `.gitignore`, `.dockerignore`, `.env.example`, and production CI.
- Production rejects example/default secrets and requires independent session, runtime-encryption,
  and audit-signing keys.
- Public, OIDC, AI, screenshot, and OIDC logout endpoints meet the documented HTTPS/origin rules.
- Production allowed hosts and trusted proxy networks contain no wildcard; the public host is allowed.
- Forwarded client/host/proto data is interpreted only from a configured proxy peer and malformed
  chains are ignored.
- Request IDs are bounded and safe before being copied into response headers.
- Local manifests and ZIPs reject SSRF targets, embedded credentials, traversal, links, encryption,
  duplicate/case-colliding names, excessive entries, and excessive expansion.
- The runtime image imports RegHub from the installed wheel and does not shadow it with a copied
  source tree.
- The runtime image uses a non-root user; CI smoke runs it read-only with dropped capabilities,
  `no-new-privileges`, and a bounded writable `/tmp` tmpfs.
- Startup migration and seed execution is serialized by PostgreSQL advisory lock and has a timeout.
- `python -m scripts.security_static_check`, `verify_release_tree`,
  `verify_production_config`, and `verify_alembic_heads` pass.
- Exactly one Alembic head exists and PostgreSQL migration/seed validation passes.
- Installed third-party dependencies pass `pip check` and strict `pip-audit`; the private RegHub
  distribution is the only excluded project package.
- Full pytest coverage remains at least 70%, and both `quality-and-integration` and `docker-smoke`
  GitHub Actions jobs are green before promotion.
