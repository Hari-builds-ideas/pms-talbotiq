# Deployment — the free demo, and the honest path to production

Two things live here: (1) the **free public demo** (Vercel + Render + Gemini) that's already prepared and
one-click, and (2) what it would take to run this **for real** for a paying tenant.

---

## Part 1 — The free demo (prepared; ~10 min of clicking)

The full step-by-step is **`DEPLOY_DEMO.md`** in the repo root. It's prepared so deployment is
configuration, not coding. The three files that make it work:
- **`render.yaml`** — a Render Blueprint: the Django web service (Docker, `config.settings.prod`,
  `deploy_migrate` as a pre-deploy step), a free Redis (key-value), and a MySQL 8 private service.
- **`vercel.json`** — builds the SPA and proxies `/api/*` → your Render host (so the browser talks to one
  origin → **no CORS**). One line to edit: the Render hostname.
- **Gemini** — `apps/ai/gemini_provider.py`; set `LLM_PROVIDER` + paste `GEMINI_API_KEY` in the Render
  dashboard. It's the **only** secret entered by hand — never in git.

**Shape:** Vercel (static SPA + proxy) → Render web (gunicorn/WSGI) → Render MySQL + Redis; Celery runs
**eagerly in-process** (Render's free tier has no background worker).

**Free-tier tradeoffs (documented honestly, don't be surprised):**
- The web service **sleeps** after ~15 min idle → a ~30–60s cold start on the first hit.
- The demo MySQL is **ephemeral** (no paid disk) → data resets on redeploy; it **reseeds on boot**, so the
  demo is always populated but nothing you change there is durable.
- Celery is **eager** → heavy AI (review drafts, JD) runs inside the request and can take longer; fine for
  a demo, not for load.
- One Redis instance for broker + cache + sessions; Gemini free tier has **rate limits**.

> Security note carried from the build: do **not** log into anyone's Vercel/Render account for them or
> commit any key. The files make it one-click; a human pastes the Gemini key in the dashboard.

---

## Part 2 — The path to real production (what changes)

The app is already built to production shape (WSGI/gunicorn, `config/settings/prod.py`, health/readiness
probes at `/healthz` `/readyz`, Prometheus `/metrics`, an advisory-locked `deploy_migrate`, a
read/write DB router, atomic cross-replica AI budgets). `docker-compose.prod.yml` is the reference
topology. To go from demo → production:

1. **Durable, backed-up MySQL 8** (managed: RDS/Cloud SQL/PlanetScale-compatible). Point-in-time restore.
   The append-only AuditLog makes durable storage non-negotiable.
2. **A real Celery worker + beat** (own process/dyno) and set `CELERY_TASK_ALWAYS_EAGER=false`, so slow AI
   never blocks a request. Redis (or managed equivalent) as broker.
3. **Secrets in a manager** (not env pasted by hand): the `DJANGO_SECRET_KEY`, DB creds, and the LLM key.
   Rotate the demo key before any real use.
4. **Always-on web** (no sleep) behind TLS + a real domain; run **≥2 web replicas** — the app is
   replica-safe (stateless workers, DB-backed sessions, atomic budgets, advisory-locked migrations).
5. **A read replica** (optional) — the DB router already sends reads to `replica` and falls back to primary
   when absent, so this is config-only.
6. **Observability**: scrape `/metrics`, alert on the `pms_ai_budget_total{outcome="redis_down"}` degrade
   metric and on `/readyz`. Ship logs.
7. **A real per-$ AI cost cap** if AI cost matters (today's cap is per-tenant *call-count* + a global
   `LLM_MAX_CALLS` ceiling — see `OPEN_QUESTIONS.md`).
8. **CI**: run `pytest` + `vitest` + `tsc` on every PR; block merge on red. `deploy_migrate` on release.

None of this is a rewrite — it's provisioning + config. The invariants (tenant isolation, RBAC, HITL,
append-only audit, one LLM gateway) already hold in every environment.
