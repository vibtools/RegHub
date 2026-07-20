# Coolify Deployment

1. Create a Dockerfile application from the repository.
2. Assign domain `reghub.ygit.dev` and enable HTTPS.
3. Attach a PostgreSQL resource and set `DATABASE_URL` with the internal hostname.
4. Set `APP_ENV=production`, `PUBLIC_BASE_URL=https://reghub.ygit.dev`, secure secrets, and OIDC values.
5. Register `https://reghub.ygit.dev/auth/callback` in `auth.vib.tools`.
6. Health check: `/api/v1/health`; readiness: `/api/v1/ready`.
7. Configure scheduled PostgreSQL backups and reverse-proxy rate limits for `/api/v1`.

Do not expose the PostgreSQL port publicly and do not commit any Coolify or OIDC token.
