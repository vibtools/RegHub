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
