# Runbook

## Local checks

```sh
cd backend && pytest -q
cd ../dashboard && npm ci && npm run build
```

Docker-based checks require Docker Engine and a populated local `.env` from `.env.example`. Never use example credentials in production. Apply database migrations with `alembic upgrade head` before starting the API.

## Incident basics

If credentials may be exposed, revoke and rotate them through the deployment secret manager. Preserve request IDs and sanitized logs. Do not copy tokens or request bodies into tickets. Verify `/health/live` and `/health/ready` after recovery.
