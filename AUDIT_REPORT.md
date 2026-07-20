# RegHub v0.1.0 — Audit Report

## Scope audited

- FastAPI application structure and internal imports
- SQLAlchemy models and relationship mappings
- PostgreSQL DDL compilation
- Alembic initial migration offline SQL generation
- Registry SDK rules
- GitHub URL normalization and SSRF boundary
- Minimal manifest validation
- Template publication invariants
- OIDC configuration and signed administrator cookie logic
- SQLAdmin custom GitHub import CSRF protection
- Secret-pattern scan
- Docker/Coolify configuration review

## Automated results

- Python compile check: PASS
- Unit tests: 15 passed
- ORM mapper configuration: PASS
- PostgreSQL table DDL compilation: PASS
- Alembic `upgrade head --sql`: PASS
- Internal application import graph: PASS
- SQLite model CRUD smoke test: PASS
- Secret-pattern scan: PASS

## Security controls implemented

- HTTPS-only `github.com` repository URLs
- Credentials, custom ports, query strings, fragments, and extra path segments rejected
- No Git clone or repository code execution
- OIDC Authorization Code flow through Authlib with PKCE S256
- OIDC admin-claim allowlist
- Signed, short-lived, HttpOnly administrator cookie
- Local redirect validation
- Trusted-host and restricted CORS configuration
- Security headers
- Session-bound CSRF token for custom GitHub import
- Draft-only imports and action-only publication
- Manifest repository, branch, and framework consistency checks before publication
- Production startup fails closed when OIDC or secure-cookie configuration is incomplete

## Remaining deployment-time verification

The following checks require the real Coolify/PostgreSQL/auth.vib.tools environment and are not reproducible inside the artifact sandbox:

- Docker image build and container startup
- Live PostgreSQL migration execution
- OIDC discovery, callback, claim mapping, and logout behavior
- Live GitHub API import and rate-limit behavior
- Coolify reverse-proxy headers, HTTPS, health checks, and backup configuration
- End-to-end YGIT API consumption

These are documented in `docs/09_COOLIFY_DEPLOYMENT.md` and `docs/11_RELEASE_CHECKLIST.md`.
