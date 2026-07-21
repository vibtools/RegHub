# RegHub v0.2.3.1 Settings, API Check & Terminal Hotfix — Production Audit

## Baseline and zero-freedom compatibility

- Built directly from the live v0.2.3 Operations & API Access source archive.
- No existing endpoint, OIDC route, SQLAdmin model view, feature flag, integration setting, encrypted
  credential, service token, block rule, operation history, template record, manifest, migration,
  Docker entrypoint, Coolify variable, or deployment boundary was removed.
- Existing database revision remains `20260721_0005`; this hotfix requires no migration.

## Forensic findings and corrections

### Settings tab reset

HTML fragments are not submitted with form POST requests. v0.2.3 depended on the URL fragment and
browser session storage, so after an action the server rendered the default Feature controls pane.
v0.2.3.1 records the originating pane in a hidden `return_tab` field, validates it server-side, and
renders the same pane after success or failure.

### API check routing failure

Inside a SQLAdmin custom view, `request.app` refers to the mounted SQLAdmin Starlette application,
not the root FastAPI application. The v0.2.3 checker sent `/api/v1/*` requests to that sub-app, whose
error template then failed to resolve `admin:statics`. v0.2.3.1 explicitly uses the root application
stored on the Admin instance and returns structured per-route results.

### Terminal spacing and diagnostics

The previous log markup placed an optional data element in an already occupied CSS grid column. The
browser created an implicit second row, producing large blank gaps. The hotfix uses one compact row
with a single content cell and inline structured diagnostics. Import and sync operations also record
redacted input context, source metadata, analyzer results, change sets, media counts, transaction
stages, elapsed time, exception stage, and bounded traceback data.

## API endpoint management

- Dedicated endpoint registry lists every supported v1 route.
- Each row has a no-reload **Check** action.
- Each row has a **Use** action that copies URL, method, scope, Bearer header, PowerShell example, and
  curl example.
- Dynamic template routes use a published template when available and are marked unavailable rather
  than falsely failed when no published template exists.
- Internal checks use short-lived in-memory tokens and never expose stored service-token secrets.

## Automated verification

Final evidence is recorded in `RELEASE_VERIFICATION_V0.2.3.1.txt`. Browser behavior through the live
Coolify reverse proxy must still be verified after deployment.
