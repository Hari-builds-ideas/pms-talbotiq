# DEPLOY_PLANS.md — two separate deployment plans

Two clearly-separated plans. **Do not confuse them:** Plan A is the free, throwaway setup for the
July 16 expo demo; Plan B is the real thing for paying tenants later. Everything below is grounded in the
actual code — `docker-compose.yml` (dev), `docker-compose.prod.yml` (the prod reference topology),
`render.yaml`, `vercel.json`, and `config/settings/`.

The stack (both plans): Django 4.2 + DRF on **gunicorn/WSGI** (`config.wsgi`, `gunicorn.conf.py`), **MySQL 8**
(locked — not Postgres), **Redis 7**, **Celery** worker + beat for background AI jobs, a **provider-agnostic
LLM gateway** (Gemini is the configured provider), and a **React/Vite SPA** (`frontend/`).

---
---

# PLAN A — DEMO DEPLOYMENT (free, for the July 16 expo)

**Goal:** a live, shareable URL a CEO can open and click through. Free tier only. Not durable, not scaled —
and that's fine for a demo.

**Shape:** SPA on **Vercel (free)** → backend + MySQL + Redis + Celery on **Render (free)** via the
committed `render.yaml` Blueprint. The SPA calls same-origin `/api/*`, which Vercel rewrites to the Render
host (`vercel.json`) — so **no CORS**.

```
Browser ──▶ Vercel (static SPA + /api proxy) ──▶ Render web (gunicorn) ──▶ MySQL (private svc) + Redis
                                                        └─ Celery runs EAGER in-process (no free worker)
```

## The Redis question, answered for the DEMO
**One small Redis instance is enough — and it is required, not optional.** Redis isn't the overkill; the
*managed / HA / two-separate-instances* setup is. Here's why one instance is correct here:
- Celery (the background AI jobs — review drafts, JD generation) uses Redis as its **broker** (and result
  backend): `CELERY_BROKER_URL=redis://…/0` (`config/settings/base.py:344`).
- The app also uses Redis for the **cache** (`…/1`) and **sessions** (`…/2`)
  (`base.py:202-232`, `SESSION_ENGINE=cache`).
- At demo volume (one presenter, a handful of clicks) all three logical DBs sit happily on **a single
  small Redis** — one Render free key-value instance. You do **not** need two instances or a managed tier.
- *(Minor caveat, immaterial for a demo:* on ONE instance every logical DB shares one eviction policy;
  production splits them because the broker must never evict a queued job while the cache wants to evict —
  see Plan B. At demo scale nothing is under memory pressure, so it never matters.)*

> Note: on Render's **free** tier there's no background worker dyno, so `render.yaml` sets
> `CELERY_TASK_ALWAYS_EAGER=true` — AI jobs run **inline in the web request** instead of on the broker.
> Redis is still used for cache + sessions. That's the cheapest correct demo shape.

## The DB (free path — MySQL, not Postgres)
Render's free managed DB is **Postgres**, but this app is **locked to MySQL 8**. So `render.yaml` runs
**MySQL 8 as a private service from the `mysql:8` image, with no paid disk** → the demo DB is **ephemeral
(resets on restart)**. Mitigation: **reseed on boot** — the demo comes up populated every time via
`seed_demo_rich`. No paid services. (For a durable demo later, attach a paid disk — the commented `disk:`
block in `render.yaml` — or a small managed MySQL.)

## One-click-ish steps
1. **Render → New → Blueprint →** point at this repo. It reads `render.yaml` and creates: the web service
   (Docker, `config.settings.prod`, `deploy_migrate` as pre-deploy), a **free Redis** (key-value), and the
   **MySQL 8** private service.
2. After the first deploy, set two host vars on the web service: `DJANGO_ALLOWED_HOSTS` = the Render host,
   `DJANGO_CSRF_TRUSTED_ORIGINS` = your Vercel URL.
3. **Paste the one secret:** `GEMINI_API_KEY` on the web service → Environment (it's `sync:false`, never in
   git). Models default to `gemini-pro-latest` (best) / `gemini-2.5-flash` (fast); on a tight free tier set
   `GEMINI_MODEL=gemini-2.5-flash` to force the cheap model.
4. **Vercel → New Project →** this repo. Edit the `/api` rewrite host in `vercel.json` to your
   `*.onrender.com` host. Deploy.
5. Open the Vercel URL. Log in with the demo accounts (tenant `acme`, password `Passw0rd!demo`):
   `admin@acme.test` · `priya@acme.test` (HRBP) · `ada@acme.test` (Manager) · `akhil@acme.test` (Employee).

## Env vars (Render web service)
| Var | Set by | Notes |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | blueprint | `config.settings.prod` |
| `DJANGO_SECRET_KEY` | Render auto-generate | — |
| `DJANGO_ALLOWED_HOSTS` / `DJANGO_CSRF_TRUSTED_ORIGINS` | **you** | Render host / Vercel URL |
| **`GEMINI_API_KEY`** | **you — hand-paste** ⚠ | the only real secret; never committed |
| `LLM_PROVIDER` | blueprint | `apps.ai.gemini_provider.GeminiProvider` |
| `CELERY_TASK_ALWAYS_EAGER` | blueprint (`true`) | AI runs inline (no free worker) |
| `LLM_MAX_CALLS` | blueprint (`200`) | demo-wide 24h cost cap |
| `DB_*` / `REDIS_*` / `CELERY_*` | blueprint (wired) | from the Redis + MySQL services |

Full detail + the one-command Gemini verify is in **`DEPLOY_DEMO.md`**.

## Free-tier honesty (don't paper over)
- **Web sleeps after ~15 min idle → ~30–60s cold start on first hit.** Mitigation: **hit the URL a minute
  before you present** so it's warm.
- **Ephemeral DB** — resets on restart; reseeds on boot (so it's always populated, but nothing you change
  persists).
- **Eager Celery** → a review draft on the best (thinking) Gemini model can take ~15–20s inline. Fine for a
  demo; not for load.
- One Redis for broker+cache+sessions; Gemini free tier has rate limits.

---
---

# PLAN B — PRODUCTION DEPLOYMENT (real users, later)

**Scale target:** 5k–15k employees per tenant, many tenants. This is provisioning + config, **not a
rewrite** — the app is already built to production shape (WSGI/gunicorn, `config/settings/prod.py`,
health/readiness probes `/healthz` `/readyz`, Prometheus `/metrics`, an advisory-locked `deploy_migrate`,
a read/write DB router, atomic cross-replica AI budgets). `docker-compose.prod.yml` is the reference
topology.

```
            ┌─ TLS/LB ─┐
Browser ──▶ │  CDN/SPA │ ──▶ web (gunicorn) ×N replicas ──▶ managed MySQL 8 (primary + optional replica)
            └──────────┘        │                      └──▶ managed Redis (BROKER)  ← noeviction, HA
                                 ├─ celery-worker ×M ───────▶ managed Redis (CACHE/SESSIONS) ← allkeys-lru, HA
                                 └─ celery-beat ×1
        secrets manager · monitoring/alerts · SMTP · Gemini data sign-off
```

## The Redis question, answered for PRODUCTION (why it's NOT overkill at scale)
At real load Redis **must** be managed, HA, and **split into two instances** — this is exactly what
`docker-compose.prod.yml` already models (`redis-broker` + `redis-cache`, lines 118-126). Three concrete
reasons, contrasting with the demo:

1. **Conflicting eviction policies — the decisive one.** The Celery **broker** holds queued/in-flight AI
   jobs; it runs `--maxmemory-policy noeviction` so a memory spike **never silently drops a job**
   (`docker-compose.prod.yml:120`, and `base.py:199` "must be noeviction"). The **cache** runs
   `--maxmemory-policy allkeys-lru` — it's *supposed* to evict cold keys (`prod.yml:126`). **One instance
   can't be both.** On the demo's single instance you pick one policy and accept the compromise because
   volume is trivial; at 5k–15k employees you can't — mixing them either loses jobs (noeviction cache
   fills up and blocks) or drops queued work (lru broker). So you split.
2. **Volume + isolation.** Many tenants running review/JD/feedback AI jobs generate real broker throughput;
   cache + session traffic is a different, bursty load. Separate instances stop cache churn from starving
   the job queue and let you size each independently.
3. **Durability + HA.** In-flight jobs and live sessions can't vanish on a node failure → managed Redis
   with replication/failover (ElastiCache, Memorystore, Redis Cloud). The demo's single free Redis has
   none of that, which is acceptable *only* because a demo can be restarted at will.

**Bottom line:** one small Redis is right for the demo; **two managed, HA Redis instances (broker vs
cache/sessions) is right — not overkill — for production**, driven primarily by the noeviction-vs-lru
policy conflict the code already relies on.

## The real shape (provision this)
- **Managed MySQL 8** (RDS / Cloud SQL / a MySQL-compatible managed service — Postgres is not an option;
  the stack is MySQL-locked). Automated **backups + point-in-time restore** (the append-only AuditLog makes
  this non-negotiable), a **connection pooler** (many gunicorn+celery connections), and an **optional read
  replica** — the DB router (`apps/core/dbrouter.py`) already sends reads→`replica`, writes→`default`, and
  falls back to primary when absent, so adding one is **config-only**.
- **Managed Redis ×2** (broker `noeviction` + cache/sessions `allkeys-lru`), HA — see above.
- **Container host** for `web` (gunicorn, **≥2 replicas** — the app is replica-safe: stateless workers,
  DB/redis-backed sessions, atomic budgets, advisory-locked migrations), `celery-worker` (**≥2**, scale to
  AI job volume), and **`celery-beat` (exactly 1)** — never eager; set `CELERY_TASK_ALWAYS_EAGER=false`.
  ECS/Fargate, Cloud Run + jobs, or k8s. `deploy_migrate` runs **once per release** (its own step), never
  in web/worker boot, so replicas don't race on schema.
- **TLS + load balancer** in front; a real domain; `DJANGO_SECURE_SSL_REDIRECT=true` (already in prod
  settings), HSTS, secure cookies.
- **Secrets manager** (not hand-pasted env): `DJANGO_SECRET_KEY`, DB creds, and the **Gemini key** —
  rotate the demo key before any real use.
- **Monitoring**: scrape Prometheus `/metrics`; alert on `/readyz` and on the
  `pms_ai_budget_total{outcome="redis_down"}` degrade metric; ship logs; track Celery queue depth + job
  failure rate.
- **Email/SMTP**: wire a real provider (invites, notifications, review/approval emails) — dev uses the
  console backend.
- **Gemini data sign-off**: a signed decision that employee performance data may egress to Google's Gemini
  API (or move to a VPC/self-hosted model), plus per-tenant AI budgets and a real $/token cap (today's cap
  is per-tenant call-count + a global `LLM_MAX_CALLS` ceiling).
- **CI**: run `pytest` + `vitest` + `tsc` on every PR; block merge on red; `deploy_migrate` on release.

## Prioritized checklist (provision vs code · rough effort · timeline)
Effort assumes one engineer familiar with the stack. **Almost all of it is provisioning/config, not code.**

| # | Item | Type | Effort |
|---|---|---|---|
| 1 | Managed MySQL 8 + backups/PITR + pooler | provision | 1–2 d |
| 2 | Managed Redis ×2 (broker noeviction + cache lru), HA | provision | 0.5–1 d |
| 3 | Container host: web ×2, worker ×2, beat ×1; `deploy_migrate` release step; eager=false | provision | 2–3 d |
| 4 | TLS/LB + domain + `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` | provision | 0.5 d |
| 5 | Secrets manager + rotate Gemini/DB/secret-key | provision | 0.5–1 d |
| 6 | Monitoring: /metrics scrape, alerts, log shipping, queue-depth | provision | 1–2 d |
| 7 | SMTP/email provider wired | provision + light code | 0.5–1 d |
| 8 | CI gates (pytest/vitest/tsc) + release pipeline (deploy_migrate) | code/config | 1–2 d |
| 9 | Gemini data-egress sign-off + per-$ AI cost cap | decision + light code | policy + 1–2 d |
| 10 | Optional: read replica (router already supports) | provision | 0.5 d |
| 11 | Load test at target scale (5k–15k/tenant); tune gunicorn/worker counts | test | 2–3 d |

**Realistic timeline:** a small production cutover is roughly **2–3 weeks** of one engineer's focused work
(items 1–8), plus the Gemini data sign-off (item 9) which is a **business/legal decision, not eng time**.
None of it is a rewrite — the invariants (tenant isolation fail-closed, server-side RBAC, HITL, append-only
audit, one LLM gateway, no fabrication) already hold in every environment; production is about durability,
scale, secrets, and observability around the existing app.

---
*See also: `DEPLOY_DEMO.md` (the demo click-through in full) and `docs/handoff/DEPLOYMENT.md`.*
