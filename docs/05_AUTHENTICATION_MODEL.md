# Authentication and Authorization Model

RegHub uses Authorization Code OIDC through `auth.vib.tools`. Authlib validates the authorization
response and ID token through discovery metadata. A short-lived signed HttpOnly cookie carries the
administrator subject, display data and resolved RegHub roles.

## Roles

- Viewer — registry and operation visibility.
- Editor — metadata edits, imports, sync and media tasks.
- Publisher — Editor permissions plus publication lifecycle.
- Security Admin — Settings, API policy, audit and operation administration.
- Super Admin — all permissions.

`reghub-admin` remains a Super Admin mapping for backward compatibility. Role claim paths and values
are configurable. Every mutating route performs a server-side permission check; UI visibility alone
is never the security boundary.


## v0.3.1.0 session stabilization

`reghub-admin` remains a Super Admin role mapping. However, old/versionless cookies that omit verified
roles are no longer trusted and never receive an inferred privileged role. The first request after
deployment may require a normal OIDC login.

The unchanged `SESSION_SECRET` acts as root material, while OIDC state, the administrator cookie, and
the SQLAdmin auxiliary session receive independent purpose-bound derived keys. This introduces no new
environment variable or deployment step. Logout clears all three local cookies and uses the existing
`OIDC_END_SESSION_URL` when configured.
