# RegHub v0.3.1.1 Release Manifest

## Release identity

- Version: `0.3.1.1`
- Classification: **Final Stabilization Hotfix**
- Baseline: `v0.3.1.0` commit `4f562f6e9c463c22a414eabcf376265c5d0c4484`
- Database migration: `20260722_0008_final_stabilization_hotfix`
- Deployment workflow: unchanged

## Zero-freedom scope

This release contains only the unfinished items identified by the v0.3.1.0 patch-validation
report. It adds no feature, API, table, column, service, integration, provider, Setting, administrator
page, worker, automation, dependency, deployment behavior or architecture change.

## Completed stabilization items

### Repository cleanup

- Removes the tracked `build/` and `dist/` trees.
- Removes root compatibility, inventory and release-verification generated artifacts.
- Removes unused Cloudflare, Coolify and Docker placeholder integration files.
- Leaves one runtime source tree: `app/`.

### Historical analysis normalization

- Removes generated `build_command`, `start_command`, `deploy_type` and `environment` fields.
- Removes obsolete deployment-readiness quality dimensions.
- Removes obsolete Docker/environment evidence flags.
- Normalizes current template analysis, template-version snapshots and import-history snapshots.
- Synchronizes nested template quality data with the canonical template quality columns.
- Recalculates historical snapshot quality using the existing registry-only dimensions.
- Uses deterministic `IS DISTINCT FROM` updates, making repeated execution safe.

### Compatibility

- Keeps framework, language, package-manager, license, README, topics and repository metadata.
- Keeps all public API routes and response models.
- Keeps authentication, OIDC, admin, publishing, import, sync, assets and manifest behavior.
- Keeps Dockerfile, GitHub Actions, entrypoint and Coolify workflow unchanged.
- Adds no new environment variable or manual database step.

## Upgrade contract

```text
Download release
→ Replace files
→ git add -A / commit / push
→ existing GitHub Actions
→ Coolify deploy
```

The existing entrypoint applies migration `20260722_0008` and seed data automatically.

## Release gate

Promotion requires the unchanged CI workflow to pass, including Ruff, formatting, compilation,
Alembic migration, seed, tests, dependency audit and Docker smoke validation.
