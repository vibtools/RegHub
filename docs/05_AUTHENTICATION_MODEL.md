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
