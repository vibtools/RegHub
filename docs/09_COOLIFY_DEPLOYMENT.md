# Coolify Deployment

1. Create the web application from the repository and attach `reghub.ygit.dev` with HTTPS.
2. Attach private PostgreSQL and set `DATABASE_URL` with the internal hostname.
3. Configure production OIDC and secure secrets; register `/auth/callback` in `auth.vib.tools`.
4. First deploy v0.3.0 with `OPERATION_BACKEND=inprocess` to preserve the current service topology.
5. Health: `/api/v1/health`; readiness: `/api/v1/ready`.
6. Configure scheduled PostgreSQL backups and verify restore procedures.
7. Configure `TRUSTED_PROXY_NETWORKS` with the real Coolify proxy network, not arbitrary client
   networks.

Optional durable mode:

- Create a private persistent Redis resource.
- Deploy a second service from the same image with `python -m scripts.worker`.
- Set the same `DATABASE_URL`, `REDIS_URL`, runtime credentials and OIDC-independent configuration on
  web and worker.
- Set `OPERATION_BACKEND=redis`; Redis cache/rate limiting are also recommended.
- Confirm worker heartbeat in readiness and `/admin/governance`.

Never expose PostgreSQL or Redis publicly and never commit Coolify, OIDC, provider or encryption
secrets.
