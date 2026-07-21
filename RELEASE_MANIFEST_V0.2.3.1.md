# RegHub v0.2.3.1 Release Manifest

## Baseline

- Built directly from the live v0.2.3 Operations & API Access release.
- Preserves every existing public API route, SQLAdmin model page, runtime feature flag, integration,
  encrypted credential, service token, IP block rule, operation record, template record, Keycloak
  route, Coolify variable, migration, and deployment boundary.
- No database migration is required.

## Hotfix scope

- Settings tab state survives every POST action and validation result.
- API verification targets the root FastAPI application rather than the mounted SQLAdmin app.
- API Manage contains a complete endpoint registry with asynchronous per-row checks and secure
  copy-ready usage instructions.
- Operation logs provide redacted input context, provider/source details, analyzer output, detected
  changes, media counts, database transaction stages, elapsed times, exception stages, and bounded
  traceback data.
- Terminal rows are compact and do not create an empty second grid row for log records without data.

## Security

- Existing service-token secrets remain one-time display only.
- The Use button copies a replacement placeholder unless a newly-created token is still visible.
- Internal checks use short-lived in-memory check tokens.
- Operation payloads and tracebacks are filtered for service-token, bearer, GitHub PAT, password,
  credential, secret, and API-key fields before administrator display.
