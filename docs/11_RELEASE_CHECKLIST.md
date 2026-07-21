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
