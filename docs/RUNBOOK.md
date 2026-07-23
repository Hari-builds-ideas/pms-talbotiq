# RUNBOOK — Talbotiq PMS

How to run, seed, log in, toggle AI, run tests, and where things live. The whole
product is one Docker stack with the React frontend on the real API.

## Run the stack

```bash
docker compose up -d --build          # mysql, redis, web (gunicorn+auto-migrate), celery-worker, celery-beat, flower, frontend (nginx edge)
docker compose run --rm web python manage.py seed_demo   # idempotent — safe to re-run
```

- **Public entry:** http://localhost:8090 (the frontend nginx serves the SPA and proxies `/api`, `/admin`, `/accounts`, `/static`, `/healthz`, `/readyz` → `web:8000`).
- **Health:** `curl http://localhost:8090/readyz` → `200`.
- **Flower (Celery):** the `flower` service (task monitoring).
- `web` has the repo bind-mounted (`.:/app`); after a backend code change run `docker compose restart web` to reload gunicorn.

## Log in (demo accounts)

Password for everyone: **`Passw0rd!demo`**. The login "Workspace" field is the **tenant slug**.

| Role | acme (FULL_AI) | globex (STARTER) |
|------|----------------|------------------|
| Admin | `admin@acme.test` | `admin@globex.test` |
| HRBP | `priya@acme.test`, `dan@acme.test` | `priya@globex.test` |
| Manager | `ada@acme.test` (4 reports) | `ada@globex.test` |
| Employee | `reza@acme.test`, `mia@…`, `sam@…` | `reza@globex.test` |

The Admin Hub is Manager-and-up by design; employees get a personal cockpit.

## Turn AI on / off (Groq)

AI runs through the single `LLMGateway` (CLAUDE.md rule 6). The provider is
`settings.LLM_PROVIDER`.

- **On (current):** `LLM_PROVIDER=apps.ai.groq.GroqProvider` with `GROQ_API_KEY` set in the gitignored backend `.env`. The stack interpolates it via compose (`${GROQ_API_KEY}`).
- **Off (graceful 503):** unset the key (or set `LLM_PROVIDER=apps.ai.providers.NotConfiguredProvider`). Every agent then surfaces a calm **503 / "AI not configured"** and never fabricates output — the manual paths still work.
- **Guards:** a global per-run call ceiling (`LLM_MAX_CALLS`, default 60, Redis-counted), bounded `LLM_MAX_TOKENS` (900), a two-model map (`LLM_MODEL_MAP`: 70B for human-read agents, 8B for chat), and 429 back-off. See `docs/AI_GOLIVE.md` to take it to production.
- **`.env` is never committed** — confirm with `git check-ignore .env`.

## Mocks (frontend)

The frontend builds against the real API by default (`VITE_USE_MOCKS=false`, set
in the compose `frontend` build args). For pure-frontend work against MSW mocks,
run the dev server with `VITE_USE_MOCKS=true` (the typed API client is identical
either way; only the transport changes). The Topbar shows a "Preview role"
switcher only in the mock build.

## Run the tests

```bash
# Backend (pytest-django + factory_boy), inside the web container:
docker compose exec -T web python -m pytest -q            # ~1059 tests

# Frontend gates (from frontend/):
cd frontend
npm run typecheck     # tsc --noEmit
npm run lint          # eslint .
npm test              # vitest run — 25 tests (error mapper, RBAC/flag gating, HITL, weights)
npm run build         # tsc + vite build

# End-to-end smoke (stack must be up + seeded), from repo root:
python3 scripts/smoke.py    # 47 journeys across every surface + RBAC boundaries
```

## Where things live

- **Backend apps** (`apps/<module>/`): `models.py`, `serializers.py` (the payload authority), `views.py`, `urls.py`, `services.py`, `tests/`.
  - `apps/ai/` — the LLM layer: `gateway.py` (the single choke), `groq.py` (provider), `agent_config.py` (per-agent prompts, settings-overridable), `evidence.py` (evidence builders), `schemas.py` (output validation), `agents/` (Agent 1–5 + chat + kpi nudges).
  - `apps/rbac/` — `matrix.py` (capabilities) + `scope.py` (data scope). The server-side authority for "who can do/see what".
  - `apps/core/management/commands/seed_demo.py` — the idempotent demo seeder.
- **Frontend** (`frontend/src/`): `lib/api/endpoints.ts` (the typed client — 1:1 with backend endpoints), `lib/types.ts`, `lib/errors.ts` (error-code mapper), `lib/auth/` (auth + refresh), `app/` (router, nav, guards, shell), `features/<area>/` (the screens), `components/` (shared UI).
- **Docs:** `docs/AI_GOLIVE.md` (authoritative AI doc), `docs/AGENT_ARCHITECTURE.md`, `docs/SSO.md`, `docs/AI_ROBUSTNESS.md`, `DECISIONS.md` (ADR log).
- **Deploy + test:** `docs/DEPLOYMENT_GUIDE.md`, `docs/TESTING_GUIDE.md`.

## Production deploy posture (BUILD_4)

`docker-compose.prod.yml` is the production CONFIG (it provisions nothing — point
it at managed MySQL/Redis for a real deploy). It runs `config.settings.prod`
(DEBUG off, HSTS, secure cookies, fail-closed secrets), a BAKED image (code
COPYed in, `INSTALL_DEV=false`, no source mount), a SEPARATE cache Redis
(allkeys-lru) from the broker Redis (noeviction), and **controlled migrations**.

**Deploy order (migrate once → roll web):**

```
# 1. Provide secrets via env / vault (compose REFUSES to start without them):
export DJANGO_SECRET_KEY=...        # long + random
export DJANGO_ALLOWED_HOSTS=app.example.com
export DB_PASSWORD=...  DB_ROOT_PASSWORD=...
# 2. Build the baked prod image:
docker compose -f docker-compose.prod.yml build
# 3. Run migrations ONCE (the only place they run in prod — no N-replica race):
docker compose -f docker-compose.prod.yml run --rm migrate
# 4. Roll the web + workers (they do NOT auto-migrate; they wait for `migrate`):
docker compose -f docker-compose.prod.yml up -d
```

The web container in prod runs gunicorn ONLY — it never migrates. (Dev keeps the
one-command `migrate && gunicorn` for convenience.) `manage.py check --deploy` is
clean under prod settings; the only residual warning (`security.W009`, weak
SECRET_KEY) clears once a real long/random key is supplied. Secrets read from the
environment via `env(...)` — the `secret_ref` indirection is the seam for a future
vault; no secret is ever committed.

## Database: read replica + connection sizing (BUILD_3)

A read/write router (`apps/core/dbrouter.py`) is ACTIVE now: reads → the
`replica` alias, writes → `default`, with read-after-write pinning (a request/task
that has written, or any read inside a transaction, reads from the primary).

**Provisioning a real replica is config-only — no code change:**

```
# Point the replica alias at the real read replica (else it falls back to a
# second connection to the primary — which is what runs today):
DB_REPLICA_HOST=<replica-host>
DB_REPLICA_PORT=3306            # optional (defaults to the primary's)
DB_REPLICA_USER=<ro-user>       # optional (defaults to the primary's)
DB_REPLICA_PASSWORD=<ro-pass>   # optional
```

In tests the replica MIRRORS the primary's test DB (`TEST: {"MIRROR": "default"}`)
so the runner never builds a second test database.

**MySQL `max_connections` sizing** (the compose `mysql` caps at 100). With the
replica split, the PRIMARY sees writes + read-after-write + in-transaction reads;
the REPLICA sees the rest of the reads. Size each:

```
primary_peak  ≈ web_replicas × gunicorn_workers × threads      # write + RAW reads
              + celery_worker_concurrency + headroom
replica_peak  ≈ web_replicas × gunicorn_workers × threads      # steady-state reads
```

`CONN_MAX_AGE=60` + `CONN_HEALTH_CHECKS=True` apply to BOTH aliases (the replica
inherits the primary's config). Celery closes old connections after each task
(`task_postrun`), so long-lived workers don't leak/reuse dropped connections.
Raise `--max-connections` (and DB resources) before scaling past the sizing math.
