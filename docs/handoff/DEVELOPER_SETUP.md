# Developer Setup — running it locally

Goal: a new developer has the app running and is logged in within an hour. Everything runs in Docker;
you don't install Python/MySQL/Redis by hand.

## Prerequisites
- Docker + Docker Compose.
- (Optional, for live AI) an LLM key — OpenAI, Groq, or Gemini. Without one the app runs fine; AI
  surfaces just return a clean "not configured" (they never fabricate).

## Run it
```bash
git clone <this-repo> && cd pms-talbotiq
cp .env.example .env            # the real .env is git-ignored; defaults work for local dev
docker compose up -d            # web, frontend, mysql, redis, celery worker + beat, flower
./scripts/demo_ready.sh         # migrate + seed the rich demo + run the E2E smoke → "✓ DEMO READY"
```
By hand instead of the script: `docker compose exec web python manage.py migrate` then
`docker compose run --rm web python manage.py seed_demo_rich`.

Open:
- **App:** http://localhost:8080  (if 8080 is taken by another project, publish the frontend on another
  port — e.g. a one-off `docker run … -p 8090:80 pms-talbotiq-frontend` on the compose network.)
- **Flower** (Celery dashboard): http://localhost:5555 · MySQL: localhost:3307 · Redis: localhost:6380.

## Demo accounts (tenant `acme`, password `Passw0rd!demo`)
| Role | Email |
|---|---|
| Admin | `admin@acme.test` |
| HRBP | `priya@acme.test` |
| Manager | `ada@acme.test` |
| Employee | `akhil@acme.test` |

## Turning AI on (optional)
Set a provider + key in `.env`, then restart web:
- **Gemini (free tier):** `LLM_PROVIDER=apps.ai.gemini_provider.GeminiProvider`, `GEMINI_API_KEY=…`
- **OpenAI:** `LLM_PROVIDER=apps.ai.openai_provider.OpenAIProvider`, `OPENAI_API_KEY=…`
- Then: `docker compose restart web celery-worker`. See `docs/AI_GOLIVE.md`.

## Reload behaviour (important)
- **Backend** (`web`, `celery-worker`) is bind-mounted but runs gunicorn/celery **without auto-reload** —
  after backend code changes: `docker compose restart web celery-worker`.
- **Frontend** is a **built image**, not a live mount — after frontend changes: `docker compose up -d
  --build frontend` (or run vite dev separately: `cd frontend && npm run dev`).

## Run the tests
```bash
docker compose run --rm web pytest -q         # backend
cd frontend && npm ci && npm test             # frontend (vitest); npx tsc --noEmit to type-check
./scripts/demo_ready.sh                        # full E2E smoke over HTTP
```
Tests never call a live LLM (a deterministic FakeLLMProvider covers the agent graphs), so they're fast
and free.

## Where things are
- Backend: `apps/<feature>/` · settings `config/settings/{base,dev,prod,test}.py` · Celery `config/`.
- Frontend: `frontend/src/` (features in `frontend/src/features/<x>/`); shared TS in `shared/src/`.
- Infra: `docker-compose.yml` (dev) · `docker-compose.prod.yml` (prod) · `Dockerfile` (backend) ·
  `frontend/Dockerfile` (SPA/nginx) · `gunicorn.conf.py`.
- v1 scope switch: `frontend/src/app/v1.ts`.

## Commit conventions
Conventional commits (`feat|fix|refactor|test|docs|chore|…(scope): summary`, ≤72 chars) — a commit hook
enforces it. Never leave the build red; commit per change.
