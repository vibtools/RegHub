# RegHub v0.2.1 Production Readiness Audit

## Baseline and zero-freedom compatibility

- Built from the running v0.2.0 Smart Registry release.
- No existing endpoint, OIDC route, SQLAdmin section, status, model field, migration, manifest version,
  Docker entrypoint, or registry/deployment boundary was removed.
- Existing templates, IDs, slugs, publication states, curated metadata, manual assets, and API paths are
  preserved.
- Migration `20260721_0003` is additive.

## Implemented fixes

- Owner-derived Provider auto-create/update for GitHub, GitLab, and Bitbucket.
- Initial-import Sync History rows plus backfill for historical templates without sync records.
- Manual sync requester, trigger, status, revision, metadata, error, and changed-field persistence.
- Recursive media scan, README image extraction, deduplication, bounded traversal, and source-safe URLs.
- Manual Asset Gallery and preservation of manual/generated assets during sync.
- Screenshot jobs with status, attempts, retry action, result, error, metadata, and public-HTTPS safety validation.
- Public asset, freshness, change-feed, facets, filter, sorting, ETag, and Last-Modified support.

## Security controls

- Repository clone/install/build/execution remains prohibited.
- Provider metadata and recursive tree reads are bounded.
- Screenshot preview/result URLs require HTTPS and reject credentials, nonstandard ports, blocked
  hostnames, and literal private/loopback/link-local/reserved/multicast addresses. The isolated screenshot
  service must separately enforce DNS-resolution and outbound-network restrictions.
- Provider credentials and screenshot tokens are never stored in registry records.
- Imports remain Draft-only; publication remains an explicit administrator action.

## Automated verification

- Python compilation: PASS
- Ruff lint/format: PASS
- Automated tests: **69 passed**
- Application-code coverage: **64%**
- Provider auto-create and update: PASS
- Initial and manual Sync History persistence: PASS
- Manual asset add/edit/delete and synchronization preservation: PASS
- Screenshot job persistence, retry, and URL security: PASS
- Recursive/README media analysis: PASS
- Public filters, assets, freshness, facets, and change feed: PASS
- ETag/Last-Modified and conditional 304 behavior: PASS
- FastAPI route smoke test: PASS
- SQLAdmin legacy regression tests: PASS
- Alembic offline PostgreSQL SQL generation through v0.2.1: PASS
- Package wheel build: PASS

## Deployment-time verification still required

- Real Coolify image build and startup
- Live PostgreSQL migration and backup confirmation
- Keycloak callback/logout after redeployment
- Live GitHub/GitLab/Bitbucket provider requests
- Optional external screenshot-service contract, DNS/egress restrictions, and storage availability
- End-to-end YGIT consumption of assets/freshness/change-feed APIs
