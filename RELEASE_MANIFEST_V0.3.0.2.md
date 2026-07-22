# RegHub v0.3.0.2 CI Quality Gate Hotfix

## Baseline

- Baseline: v0.3.0.1 Governance UI and Redis Worker Control Hotfix.
- Runtime behavior is unchanged.
- Existing API, Settings, Governance, Operations, RBAC, audit, Redis worker controls, database records, and deployment flow are preserved.

## Correction

GitHub Actions stopped at the Ruff quality gate before tests and Docker verification. This release corrects the reported import-order, unused-import, test import-position, and unused-noqa findings.

## Database

No migration is added. Existing migration checksums are unchanged.
