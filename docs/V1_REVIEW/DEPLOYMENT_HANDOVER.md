# DEPLOYMENT_HANDOVER — production setup (for the deployment team)

Everything needed to deploy TalbotIQ PMS for real users. Grounded in the actual repo:
`docker-compose.prod.yml` (the reference topology), `Dockerfile`, `gunicorn.conf.py`,
`config/settings/prod.py`, and the root **`.env.example`** (the complete, commented variable list —
production values marked `[PROD]`, dev-only values marked). **No secrets in this repo** — you set the
real environment; placeholders only here.

## 1. Required services (the shape)
```
                    ┌── TLS / load balancer (you provide) ──┐
Browser/SPA ──HTTPS─┤  static SPA (nginx image or CDN)      │
                    └──────────────┬────────────────────────┘
                                   ▼  /api
        web (gunicorn, config.wsgi) ×2+ replicas ── managed MySQL 8 (primary [+ optional replica])
             │                                  └── managed Redis ×2:
             ├── celery-worker ×2+                    · BROKER  → maxmemory-policy noeviction
             └── celery-beat  ×1 (exactly one)        · CACHE/SESSIONS → allkeys-lru
```
- **Web**: the baked image (`Dockerfile`), started with
  `gunicorn config.wsgi:application -c gunicorn.conf.py`. Stateless — scale horizontally (the app is
  replica-safe: DB/Redis-backed state, atomic budgets, advisory-locked migrations).
- **Celery worker** (`celery -A config worker -l info`) — the AI jobs (review drafts, JD generation,
  360 summaries). **Celery beat** (`celery -A config beat -l info`) — approval escalations; run exactly
  one. Set `CELERY_TASK_ALWAYS_EAGER=false` (the `true` value is a free-demo shim only).
- **MySQL 8 (managed)** — the stack is **MySQL-locked** (not Postgres). Need: automated backups + PITR
  (the audit log is append-only and must be durable), TLS (`DB_SSL_CA`), and connection sizing:
  `peak ≈ web_replicas × gunicorn_workers × threads + celery_concurrency + headroom` (the sizing note
  is in `config/settings/base.py` at the DATABASES block). Optional **read replica**: set
  `DB_REPLICA_*` — the read/write router picks it up with no code change.
- **Redis ×2 (managed, HA)** — split is REQUIRED at production load because the two workloads need
  opposite eviction policies: the **broker must never evict** a queued job (`noeviction`) while the
  **cache is supposed to evict** (`allkeys-lru`); one instance cannot be both
  (`docker-compose.prod.yml` services `redis-broker`/`redis-cache` model this exactly).
- **Flower** (optional Celery dashboard): only behind basic auth — `FLOWER_BASIC_AUTH` with a real
  credential, never the placeholder.

## 2. Build & start
```bash
docker build -t pms-talbotiq:prod .                     # backend (baked, no dev toolchain)
docker build -t pms-frontend:prod ./frontend            # SPA (nginx) — or host dist/ on a CDN
# Reference for wiring/order (migrate → web/workers): docker-compose.prod.yml
```
Start order per release:
1. **`python manage.py deploy_migrate`** — runs migrations **once**, under a MySQL advisory lock
   (a concurrent racer no-ops), so N web replicas never race on schema. Run it as a release step / the
   `migrate` one-shot service — web and workers do NOT migrate on boot.
2. Start/roll `web`, `celery-worker`, `celery-beat`.
3. Probes: liveness `GET /healthz`, readiness `GET /readyz` (checks DB + Redis). Both unauthenticated.

## 3. Environment
Fill **`.env.example`** — every variable is documented inline. The critical ones:
`DJANGO_SETTINGS_MODULE=config.settings.prod` (fail-closed) · `DJANGO_SECRET_KEY` (required, random) ·
`DJANGO_ALLOWED_HOSTS`/`DJANGO_CSRF_TRUSTED_ORIGINS` (real domains, never `*`) · `DB_*` (+`DB_SSL_CA`) ·
the two Redis URLs + `CELERY_*` · **`EMAIL_*` + `PUBLIC_APP_URL`** (password reset depends on SMTP) ·
`GEMINI_API_KEY` + `LLM_PROVIDER` · `LLM_MAX_CALLS` sized to tenants (or `0` + a provider-side dollar
cap) · `METRICS_TOKEN` · `SENTRY_DSN` · `FLOWER_BASIC_AUTH`. Keep every secret in your secrets manager;
inject as env.

## 4. Seeding
- Fresh production DB: `deploy_migrate` creates the schema; create the first tenant + admin via
  `python manage.py shell` or the admin API (no demo data required).
- **Demo data (optional):** `python manage.py seed_demo_rich` — idempotent, creates the ACME tenant
  (~200 people, goals with recorded progress, reviews, 360s, recognition; accounts
  `admin@acme.test` / `priya@` / `ada@` / `akhil@`, password `Passw0rd!demo`). Do NOT run against a
  tenant database holding real customer data.

## 5. Third-party integrations (and their env)
- **Gemini (LLM)** — **wired and verified working end-to-end** on a real enterprise key (agent
  plan→approve, review drafts on the best model, chat memory). Provider-agnostic gateway; OpenAI/Groq
  are config-switchable alternates. No key → AI returns a clean 503, everything else works.
  Note: `gemini-2.5-pro` is blocked for new Google API projects — defaults are `gemini-pro-latest`
  (strong) + `gemini-2.5-flash` (fast), overridable by env.
- **Email/SMTP** — **wired this run** (password reset emails). Configure `EMAIL_*`; the console backend
  is the dev default.
- **Slack / Jira** — **scaffolded, NOT connected.** `apps/integrations/` has the seams (per-tenant
  webhook config, best-effort notify that silently no-ops when unconfigured). Do not present these as
  working integrations.
- **Sentry** — wired, disabled without `SENTRY_DSN`; PII scrubbed. **Prometheus `/metrics`** — enabled
  only when `METRICS_TOKEN` is set; scraper sends `Authorization: Bearer <token>`.

## 6. Monitoring (minimum)
Scrape `/metrics` (with the token) · alert on `/readyz` failures · alert on
`pms_ai_budget_total{outcome="redis_down"}` (budget layer degraded) · watch Celery queue depth + job
failure rate · Sentry for exceptions · DB backup success.

## 7. HONEST "not yet production-wired" list (know before you ship)
1. **No in-app notification system.** Notifications are Slack-only and silently no-op for tenants
   without a webhook — approvals/feedback-requests/escalations produce no user-visible alert in a
   Slack-less tenant. In-app center is a v2 build. (Password-reset email works; other email
   notifications are not built.)
2. **Refresh JWT lives in browser localStorage** (XSS-exfiltratable). Mitigations in place: 15-min
   access tokens in memory, rotation + blacklist, revocation on logout AND on password reset. The full
   fix (http-only cookie / BFF) is a v2 decision — consider shortening `JWT_REFRESH_DAYS`.
3. **No per-account login lockout** — only a per-IP throttle (`THROTTLE_ANON`). Recommend django-axes
   or an account-scoped counter before large-scale exposure.
4. **AI cost cap is call-count, not dollars** (`LLM_MAX_CALLS` + per-tenant call budgets). Set a
   provider-side spend limit on the Gemini key.
5. **Data egress sign-off**: employee performance data goes to Google's Gemini API for AI features —
   get the customer/legal sign-off, or point `LLM_PROVIDER` at an approved endpoint.
6. **Mobile app deferred to v2** (backend-ready; the Expo frontend is unfinished — `docs/handoff/MOBILE.md`).
7. **v1 scope cuts are intentional** (nine-box/calibration, succession, career, raw tenant config,
   T-score displays) — hidden behind flags, re-enable steps in `docs/handoff/V1_VS_V2.md`. Not missing
   features.

*See also `DEPLOY_PLANS.md` (demo vs production comparison, effort/timeline) and `docs/handoff/` (the
full engineering handover: system overview, dev setup, how-it-was-built).*
