# Security Model

Repository and integration URLs are HTTPS-only, credential-free and validated against public-network
boundaries. RegHub does not clone or execute imported code. OIDC, CSRF, secure cookies, TrustedHost,
restricted CORS and structured request IDs remain mandatory.

## v0.3.0 controls

- Forwarding headers are accepted only from `TRUSTED_PROXY_NETWORKS`; Uvicorn proxy parsing is
  disabled.
- Public, token, authenticated-token IP and administrator rate limits can be shared through Redis.
- Runtime credentials use a versioned Fernet keyring; previous keys support rotation.
- Governance events use a versioned HMAC signing keyring and an immutable hash chain.
- Nested token/password/authorization values are redacted from operation and audit records.
- Role checks protect all privileged tasks and retry authorization follows the original task type.

Production should use independent `SESSION_SECRET`, `RUNTIME_ENCRYPTION_KEY` and `AUDIT_SIGNING_KEY`
values, private PostgreSQL/Redis networks and reverse-proxy edge limits in addition to application
limits.


## v0.3.1.0 stabilization controls

- Legacy/versionless administrator cookies without verified roles are rejected.
- Browser security boundaries use purpose-separated derived keys.
- Logout clears all RegHub authentication/session cookies and sends a fixed public-base return URL to
  the existing OIDC end-session endpoint.
- Provider adapters preserve private-repository classification. AI enrichment checks the classification
  before orchestration and again before creating an HTTP client, so private content cannot be sent.
- Repository analysis no longer produces deployment decisions; YGIT remains the deployment owner.
