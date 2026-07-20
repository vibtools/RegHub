# Security Model

GitHub URLs are HTTPS-only, host-allowlisted, credential-free, and normalized. Repository clone is
forbidden in MVP. Production requires secure cookies, a 32+ character session secret, TrustedHost,
restricted CORS, secret storage in Coolify, and proxy-level rate limiting. Admin publication validates manifest structure and verifies repository, branch, and framework consistency before state transition. The custom import form uses a session-bound CSRF token.
