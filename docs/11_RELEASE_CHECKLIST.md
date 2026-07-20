# Release Checklist

- Tests and Ruff pass
- Alembic upgrades an empty PostgreSQL database
- Seed is idempotent
- OIDC callback and admin claim are verified
- Draft/disabled templates never appear publicly
- GitHub import rejects malformed/private/archived repositories
- No secrets exist in repository history
- Coolify health, HTTPS, logs, and backups are confirmed
