# RegHub v0.3.1.0 Release Manifest

## Release identity

- Version: `0.3.1.0`
- Classification: **Architecture Stabilization Release**
- Baseline: `v0.3.0.3` plus the formatting-only main-branch Ruff correction
- Database migration: `20260722_0007_architecture_stabilization`
- Deployment workflow: unchanged

## Scope lock

This release adds no product feature, public endpoint, integration, provider, administrator page,
Setting, service, deployment capability or automation. RegHub remains the registry service for YGIT.
Docker, GitHub Actions, Coolify, entrypoint and developer deployment commands remain unchanged.

## Stabilization contents

### Security

- Rejects versionless, malformed and roleless administrator cookies instead of inferring privilege.
- Domain-separates the existing deployment secret for OIDC state, administrator authentication and
  the SQLAdmin auxiliary session.
- Clears all local RegHub authentication/session cookies during logout and uses the configured OIDC
  end-session endpoint when available.
- Preserves private visibility through GitHub, GitLab and Bitbucket adapters and prevents private
  repository content from reaching optional AI enrichment.

### Registry boundary

- Retains framework/version, language, package manager, license, topics, README metadata, repository
  metadata, media, use case, difficulty, quality and security analysis.
- Stops generating build, start, runtime, environment, deployment-type and deployment-readiness
  intelligence. YGIT remains responsible for deployment decisions.
- Keeps Manifest v1/v2 validation and all existing public response contracts; newly generated
  manifests are deployment-neutral.

### Database integrity

- Aligns `templates.external_repository_id` with the existing 160-character model contract.
- Normalizes invalid bounded counters/scores before adding database checks.
- Removes exact duplicate template-asset rows while preserving the oldest record.
- Adds model-aligned checks and a deterministic asset identity constraint.
- Removes redundant unique indexes already covered by unique constraints.
- Cleans obsolete analyzer-generated deployment intelligence while preserving administrator-curated
  manifest overrides.
- Drops no table or column.

### Repository maintenance

- Excludes build/distribution output, caches, temporary files and generated verification evidence.
- Removes obsolete generated root reports from the tracked source package.
- Preserves substantive documentation and historical release manifests.

## Upgrade contract

The existing workflow remains authoritative:

```text
Download release
→ Replace files
→ git add -A / commit / push
→ existing GitHub Actions
→ Coolify deploy
```

The existing entrypoint applies the migration and seed automatically. No new environment variable,
service, command or manual migration step is required.

## Verification gate

Production promotion requires the unchanged GitHub Actions workflow to pass. Local release checks
cover focused stabilization tests, source compilation, template/YAML/shell validation, PostgreSQL DDL,
Alembic offline upgrade, package build, secret scanning and clean re-extraction.
