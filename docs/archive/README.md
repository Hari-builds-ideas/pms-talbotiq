# Archived deployment configs

Deployment is **GCP: a VM running `docker-compose.prod.yml`** (see the FACTS block
in `OVERNIGHT_BUILD_PROMPT.md`). The repo carried four overlapping deployment
stories, which is three more than one team can keep true — and a stale config that
still looks live is worse than no config, because someone eventually follows it.

## Moved here (not live, kept for reference)

| File | Was for | Why it moved |
|---|---|---|
| `railway.json` | Railway web service | Not the deployment target. Kept rather than deleted because the repo's history shows a Railway deploy did exist, so the exact build/start/healthcheck config is worth being able to read. |
| `railway.worker.json` | Railway celery worker | Same. |
| `railway.beat.json` | Railway celery beat | Same. |

## Deleted outright

| File | Why deleted rather than archived |
|---|---|
| `vercel.json` | It hardcoded a production API hostname (`talbotiq-pms-api-production.up.railway.app`) with no env indirection, so **any** preview deployment pointed at production. Archiving a file whose only distinctive content is a live URL aimed at prod is not worth the risk of it being copied back. |
| `render.yaml` | A free-tier demo path that set `CELERY_TASK_ALWAYS_EAGER=true`, running AI jobs inline in the web process. Not a production posture, and keeping it invites someone to deploy it. |

## What is live

- `docker-compose.prod.yml` — the stack
- `Caddyfile` — the TLS edge (see `docs/BUILD/ENABLE_TLS.md`; TLS is off until a
  domain exists)
- `Dockerfile`, `frontend/Dockerfile` — the images
- `gunicorn.conf.py` — the app server

If Railway is ever revived, move these back rather than rewriting them.
