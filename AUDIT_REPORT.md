# RegHub v0.2.0 Production Readiness Audit

## Baseline and compatibility

- Built from the running v0.1.1 replace-ready project.
- No existing endpoint, OIDC route, admin CRUD section, status, migration, model field, or Docker
  entrypoint was removed.
- Manifest v1 remains valid; new imports use Manifest v2.
- Database migration is additive.

## Security controls

- Repository clone/install/build/execution remains prohibited.
- Provider URLs require HTTPS, reject credentials, custom ports, query strings, fragments, and
  provider web-route URLs.
- Provider text metadata reads are bounded.
- GitHub PAT, GitLab token, Bitbucket app password, AI key, and screenshot token are never stored in
  registry metadata.
- Local ZIP checks include path traversal, symbolic links, encrypted entries, compressed size,
  uncompressed size, entry count, and bounded text reads.
- Local ZIP templates cannot be published until assigned a deployable HTTPS repository.
- Screenshot generation is delegated to an optional isolated external service.
- Imports remain Draft-only and publication remains an explicit administrator action.

## Automated verification

- Python compilation: PASS
- Ruff formatting/lint: PASS
- Automated tests: 59 passed
- SQLAdmin Template list/filter regression: PASS
- Framework/version/package-manager detection: PASS
- Metadata, environment, score, and category analysis: PASS
- Manifest v1/v2 compatibility: PASS
- GitHub/GitLab/Bitbucket URL validation: PASS
- Safe local manifest/ZIP processing: PASS
- Smart import and source-sync persistence: PASS
- Curated identity and publication status preservation during sync: PASS
- Alembic offline PostgreSQL SQL generation through v0.2: PASS

## Deployment-time verification still required

- Real Coolify Docker image build/start
- Live PostgreSQL migration and backup
- Keycloak callback/logout after redeployment
- Live provider API calls with production credentials
- Optional AI/screenshot service behavior if enabled
- End-to-end YGIT consumption of Manifest v2
