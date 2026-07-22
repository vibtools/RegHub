# Security Policy

Do not open public issues containing credentials or vulnerability details. Report security findings
privately to the project owner. Rotate any exposed OIDC, provider, database, screenshot, Redis,
runtime-encryption, audit-signing, or session secret immediately. Supported security updates apply
to the current `0.3.x` release line.

RegHub uses purpose-bound derived signing material for browser session boundaries. Legacy roleless
administrator cookies are rejected and must be replaced by a fresh OIDC login. Logout clears the
administrator, SQLAdmin auxiliary, and OIDC-state cookies and uses the configured identity-provider
end-session URL when available.

Private repository metadata may be imported only through an authenticated provider configuration.
Private repository content is never submitted to optional AI metadata enrichment. RegHub validates
screenshot URLs before delegation, but the isolated screenshot service must also resolve DNS safely,
block private/internal destinations after resolution, restrict outbound network access, and enforce
time, redirect, and response-size limits.
