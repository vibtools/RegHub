# RegHub v0.2.3 Release Manifest

## Baseline

- Built from the live v0.2.2.1 UI & Operations Hotfix.
- Existing public API paths, Keycloak/OIDC behavior, template IDs and slugs, publication states,
  manifests, runtime integrations, encrypted credentials, operation history, and Coolify entrypoint
  remain compatible.
- No Smart Registry feature or deployment boundary was removed.

## Release scope

- Duplicate repository imports finish as **Skipped / No change**, not Failed.
- Import and sync operations record denser developer-oriented terminal logs and exact exception types.
- Operations Console supports search, status/type/order filters, and safe terminal-history clearing.
- Asset Gallery supports template search plus asset search and kind filtering.
- SQLAdmin registry tables gain productive search, filters, date/name sorting, and sensible defaults.
- Settings navigation includes a visible **API Manage** workspace.
- API Manage provides Development/Live mode, scoped service tokens, IP/CIDR/hostname block rules,
  and authenticated in-app endpoint checks.

## Security design

- Service tokens use the `vt_reg_...` format and are displayed only once.
- Only an HMAC-SHA256 token digest, prefix, and last four characters are stored.
- Live Mode requires `Authorization: Bearer vt_reg_...` or `X-RegHub-Token`.
- Tokens can be enabled, disabled, deleted, expired, and limited by endpoint scope.
- Block rules support individual IPs, CIDRs, hostnames, localhost, and documented private-network
  wildcard aliases.
- Health, readiness, administrator authentication, Settings, and operation history remain recovery
  surfaces.

## Additive schema

Migration `20260721_0005_api_access_operations` adds only:

- `api_access_policies`
- `api_service_tokens`
- `api_block_rules`

No existing table, column, index, record, or migration is deleted or renamed.
