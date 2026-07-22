# Security Policy

Do not open public issues containing credentials, private repository content, or vulnerability
reproduction details. Report security findings privately to the project owner. Rotate any exposed
OIDC, provider, database, screenshot, Redis, runtime-encryption, audit-signing, or session secret
immediately. Supported security updates apply to the current `0.3.x` release line.

## Production security baseline

RegHub production startup fails closed unless all of the following are true:

- `SESSION_SECRET`, `RUNTIME_ENCRYPTION_KEY`, and `AUDIT_SIGNING_KEY` are independently generated,
  contain at least 32 characters, and do not use documented example values.
- `PUBLIC_BASE_URL`, the OIDC issuer, and configured credential-bearing integration endpoints use
  HTTPS. The public host must also appear in `ALLOWED_HOSTS`.
- Secure session cookies are enabled; wildcard allowed-host and trusted-proxy entries are rejected.
- PostgreSQL uses the asyncpg driver. Explicit Redis-backed operations, cache, or rate limiting
  require `REDIS_URL`.
- Private GitHub repository access requires an explicit GitHub token. Optional AI, screenshot, and
  Bitbucket credentials must be configured as complete pairs.

Keep secrets in the deployment secret store. Never commit `.env`, private keys, certificates,
database dumps, audit exports, or provider tokens. Preserve previous runtime/audit keys only for the
bounded rotation period required to read existing encrypted values and verify historical signatures.

## Authentication and browser boundaries

RegHub uses purpose-bound derived signing material for browser session boundaries. Legacy roleless
administrator cookies are rejected and must be replaced by a fresh OIDC login. Logout clears the
administrator, SQLAdmin auxiliary, and OIDC-state cookies and uses the configured identity-provider
end-session URL when available. Request identifiers are normalized before being reflected in response
headers, and production responses include HSTS, frame denial, MIME-sniffing protection, restrictive
permissions, referrer, opener, and cross-domain policy headers.

## Network and import boundaries

Forwarded client, scheme, and host values are accepted only from configured proxy networks. Invalid
forwarding chains are ignored rather than trusted. Keep the proxy allowlist limited to the actual
Coolify/reverse-proxy network; never use `*` in production.

Private repository metadata may be imported only through an authenticated provider configuration.
Private repository content is never submitted to optional AI metadata enrichment. Local manifest and
ZIP imports are bounded, never executed, and reject traversal, links, encryption, duplicate or
case-colliding paths, control characters, and private/reserved HTTPS destinations.

RegHub validates screenshot URLs before delegation, but the isolated screenshot service must also
resolve DNS safely, block private/internal destinations after every resolution and redirect, restrict
outbound network access, and enforce time, redirect, content-type, and response-size limits.

## Release and incident handling

Promote only commits for which both GitHub Actions jobs are green. The release workflow must pass
Ruff, compilation, production-config validation, repository/security static checks, a single Alembic
head, PostgreSQL migration/seed, full pytest coverage, strict third-party dependency audit, and the
read-only non-root Docker readiness smoke test.

On suspected compromise: isolate the deployment, retain logs and immutable audit data, rotate all
credentials and signing/encryption keys according to the documented rotation order, invalidate
sessions and service tokens, review provider access, verify the audit chain, restore from a known-good
backup if integrity is uncertain, and redeploy only from a verified release commit.
