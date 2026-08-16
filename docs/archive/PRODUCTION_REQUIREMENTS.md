# PRODUCTION_REQUIREMENTS — TalbotIQ PMS

**Read-only assessment.** Everything below is grounded in the actual code/config (files + lines cited).
Context: multi-tenant SaaS, many SME orgs at once, ~5k–15k employees **per tenant**, a real public site.

> **Doc-accuracy note (important):** the two "readiness" docs you'll find in the repo —
> `docs/SYSTEM_DESIGN_AND_READINESS.md` and `docs/archive/PROD_READINESS_STATUS.md` (both Jul 4) — are
> **stale on several load-bearing points.** They predate the hardening that actually landed (BUILD-2/3/4
> and "File I"). I verified against the code: the DB read/write **router, async AI offload, atomic
> cross-replica budget, controlled advisory-locked migrate, and the `/metrics` endpoint are all BUILT**
> (citations in §2/§3/§5). Where this file and those docs disagree, **this file (code-grounded) is
> correct.** `docs/AI_GOLIVE.md` (Jul 3) is the authoritative AI doc; `docs/RUNBOOK.md`,
> `docs/OBSERVABILITY.md`, `docs/CACHING.md`, `docs/QUERY_BUDGETS.md`, `docs/SSO.md` are accurate.

## 0. Executive summary
The app is **architecturally production-shaped already**: `config/settings/prod.py` is hardened
(fail-closed secrets, HSTS, secure cookies), `docker-compose.prod.yml` defines the real topology (baked
image, one-shot advisory-locked migrate, gunicorn-only web, **separate** broker/cache Redis, Sentry),
heavy AI is offloaded to Celery, list queries are N+1-guarded, and budgets are atomic across replicas.
**What's missing is mostly *provisioning* (managed MySQL, TLS/LB, a secrets store, monitoring stack, a
real IdP, an SMTP provider) plus a short list of *code* gaps** — chiefly **email/SMTP is not wired**, DB
connections aren't TLS-configured in-app, and the LLM budget is a call-count proxy, not a dollar cap.
Honest status: **ready for a controlled pilot in ~1–2 weeks; real multi-tenant scale in ~4–6 weeks**,
assuming infra is provisioned promptly. Details + checklist in §6.

---

## 1. Secrets / API keys

Every secret is read via `django-environ` `env(...)` — **no secret is hardcoded**; `config/settings/prod.py`
makes the critical ones **fail-closed** (the process refuses to boot without them).

| Secret | Purpose | Read from (env var → settings) | Required? |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | Django signing **and JWT signing** (`SIMPLE_JWT["SIGNING_KEY"]=SECRET_KEY`, `base.py:300`, re-pointed `prod.py:11,14`) | `DJANGO_SECRET_KEY` → `SECRET_KEY` (`prod.py:11`, no default → boot error if unset) | **Yes** |
| `DJANGO_ALLOWED_HOSTS` | Host allow-list | `prod.py:17` (no wildcard fallback) | **Yes** |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | CSRF origins for the SPA domain | `prod.py:30` | Yes (public site) |
| `DB_PASSWORD` / `DB_USER` / `DB_NAME` / `DB_HOST` / `DB_PORT` | MySQL creds | `base.py:148–152` | **Yes** |
| `DB_ROOT_PASSWORD` | MySQL root (compose provisioning only) | `docker-compose.prod.yml` | Only if you run DB in compose |
| `DB_REPLICA_HOST/PORT/USER/PASSWORD` | Read replica DSN | `base.py:184–190` | Optional (router falls back to primary) |
| `REDIS_CACHE_URL` / `REDIS_SESSION_URL` | App cache (/1) + sessions (/2) | `base.py:202–205` | Yes (default localhost) |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | Celery broker + results (/0) | `base.py:344–345` | **Yes** |
| **LLM key** — `OPENAI_API_KEY` (+ `OPENAI_BASE_URL`) or `GROQ_API_KEY` / generic `LLM_API_KEY`+`LLM_BASE_URL` | The AI provider key | `base.py:425–430`; provider chosen by `LLM_PROVIDER` (`base.py:414`) | Yes, to run AI (else agents 503, no fabrication) |
| `LLM_MAX_CALLS` | Deployment-wide AI call ceiling (cost backstop) | `base.py:441` (**default 500 = a dev/QA value — must be sized for prod or set 0**) | Tune for prod |
| `LANGSMITH_API_KEY` | Optional LLM tracing (no-op unset) | `base.py:416` | Optional |
| `SENTRY_DSN` (+ `SENTRY_ENVIRONMENT`) | Error tracking (no-op unset) | `docker-compose.prod.yml`; `sentry-sdk` in `requirements.txt` | Strongly recommended |
| `METRICS_TOKEN` | Bearer to expose `GET /metrics` (fail-closed → 404 if unset) | `apps/core/views.py:40–41` (`MetricsView`) | Yes (for monitoring) |
| **SMTP / email** | Password reset, allauth email, notifications | **NOT configured anywhere** — no `EMAIL_*` in `base.py`/`prod.py`; allauth `ACCOUNT_EMAIL_VERIFICATION="none"` (`base.py:311`) | **Gap — see §4** |
| Integration tokens (Slack/Jira) | Per-tenant integration creds | env by name via `apps/integrations/secrets.py:17–27`: `<KIND>_TOKEN` or per-tenant `<KIND>_TOKEN_<TENANT_SLUG_UPPER>` (e.g. `JIRA_TOKEN_ACME`, `SLACK_WEBHOOK_ACME`); unset → clean no-op | Only if integrations are enabled |
| SSO: `OIDC_CLIENT_ID/SECRET/SERVER_URL/...` | OIDC login | env (`docs/SSO.md:30–33`) | Per customer, if SSO used |
| SSO: per-tenant `SamlIdpConfig` + `sp_private_key_secret_ref` | SAML SP | DB row (public cert) + env-named private key; **no secret in DB** (`docs/SSO.md:59–76`) | Per customer, if SAML used |
| Flower basic-auth | Celery dashboard protection | compose flower command | Yes (don't expose Flower unauthenticated) |

### LLM keys — one platform key, metered per tenant (NOT per-tenant keys)
**Wired today:** a **single platform-wide provider + key** (`LLM_PROVIDER` + `OPENAI_API_KEY`/`LLM_API_KEY`,
`base.py:414,425–430`). There is **no per-tenant LLM-key wiring** (grep of `apps/ai/*` for a tenant→key
mapping returns nothing). Cost is contained **per tenant by budget, not by key**: per-tenant `AgentBudget`
(`DEFAULT_AGENT_BUDGETS` in `apps/billing/packs.py`) + append-only `TokenLedger` (`apps/billing/models.py:90`)
+ a **deployment-wide** `LLM_MAX_CALLS` ceiling (`base.py:441`), reserved **atomically across replicas** via
Redis Lua (`apps/billing/atomic.py`).

**Recommendation — what to ask the company for:** **one platform OpenAI (or internal-engine) API key** +
a **provider-side hard dollar cap** on that key (the app enforces call-count budgets, `AI_GOLIVE.md`
notes a true $-cap is a follow-up — §5). Per-tenant keys are only needed if a customer contractually
requires their own billing/DPA/data boundary — that's a **code-work** add (~1–2 days), not required for
launch. (Integration tokens *are* already per-tenant-capable via the `secret_ref` env convention.)

### Secrets vault — honest minimum vs ideal
- **Minimum to launch (acceptable):** inject secrets via the **host/platform secret store as environment
  variables** (e.g. ECS/K8s secrets, Fly/Render secrets, Docker/systemd env). The whole app already reads
  every secret from env; `prod.py` fails closed if the critical ones are missing. **A dedicated vault is
  NOT strictly required for a first controlled launch** provided secrets are injected as env (never in
  `.env` committed, never in the DB).
- **Ideal (before broad GA / real customer data):** a managed **secrets manager / vault** (AWS/GCP Secrets
  Manager, HashiCorp Vault). `apps/integrations/secrets.py::resolve_secret` is the single seam to point at
  it (`NEEDS_HARI_secrets.md`). `SYSTEM_DESIGN §6` calls the vault "required before real customer data."
- **Not acceptable:** plaintext token columns in the DB, or committing `.env`.

---

## 2. Database

- **Engine/version:** MySQL 8 (`docker-compose*.yml` `image: mysql:8.0`; `ENGINE=django.db.backends.mysql`,
  `base.py:147`), `utf8mb4`, `STRICT_TRANS_TABLES` (`base.py:165–169`). `mysqlclient==2.2.4`.
- **Connection handling (already in code):** `CONN_MAX_AGE=60` + `CONN_HEALTH_CHECKS=True` (`base.py:163–164`)
  — persistent, self-healing connections. A **sizing formula is documented in-code** (`base.py:154–162`):
  `peak_conns ≈ web_replicas × gunicorn_workers × threads + celery_concurrency + headroom`; the compose
  MySQL caps at `--max-connections=100`, "raise it (and DB resources) before scaling past that."
- **Read replica: BUILT and active** (contra the stale SYSTEM_DESIGN "NOT-BUILT"). `DATABASE_ROUTERS =
  ["apps.core.dbrouter.PrimaryReplicaRouter"]` (`base.py:195`); reads→`replica`, writes→`default`, with
  read-after-write pinning (`apps/core/dbrouter.py`). With no `DB_REPLICA_HOST`, the replica alias falls
  back to the primary — so **provisioning a real replica is config-only, no code change.**
- **TLS to the DB:** the DB `OPTIONS` (`base.py:165–169`) set charset + sql_mode but **do not set `ssl`** —
  app→DB TLS is not configured in-code today. For prod, either run the DB on a private network segment
  (acceptable) or add `OPTIONS["ssl"]` (small code change, §6). Note: the **web** tier assumes a
  TLS-terminating proxy in front (`SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO","https")`, `prod.py:21`)
  — that's HTTP TLS, separate from DB TLS.
- **Migrations: production-ready.** Run **once** at deploy via the advisory-locked management command
  `python manage.py deploy_migrate` (`apps/core/management/commands/deploy_migrate.py`, MySQL `GET_LOCK`,
  `LOCK_NAME="pms_deploy_migrate"`): the first caller migrates, concurrent callers no-op — **N web replicas
  never race on schema.** `docker-compose.prod.yml` has a dedicated one-shot `migrate` service that runs it;
  web/workers do **not** auto-migrate (`RUNBOOK.md:84–97`).

**What to provision for 5k–15k users/tenant × many tenants:**
- **Managed MySQL 8** (RDS / Cloud SQL / Aurora-MySQL), multi-AZ, with **automated backups + PITR + a
  *tested* restore drill**, sized for the connection math above. At this scale plan a **connection pooler**
  (ProxySQL / RDS Proxy) because Django holds per-worker persistent connections across many replicas.
- **A read replica is worth it at this scale** (analytics/list reads dominate) — and it's config-only to
  turn on (set `DB_REPLICA_*`). Not strictly required for a single-tenant pilot.
- **Indexing/at-scale:** shared-DB multi-tenancy (`TenantScopedModel` + tenant-scoped manager). Millions of
  rows across tenants → confirm composite indexes lead with `tenant_id`; consider partitioning the
  largest tables (audit log, token ledger, cycle scores) by tenant/time before the largest tenants land.

---

## 3. Hosting / deployment architecture

**Is Vercel appropriate?** Only for the **frontend SPA**, not the backend. Vercel hosts static/SPA and
serverless functions well, but this backend is a **long-running, stateful stack**: gunicorn/WSGI Django,
**Celery worker + beat** (persistent processes), **Redis** (broker + cache), and **MySQL** — none of which
fit Vercel's serverless model. **Split the two tiers.**

**Confirmed services (from `docker-compose.prod.yml`):**
| Service | Prod command | Notes |
|---|---|---|
| `migrate` (one-shot) | `python manage.py deploy_migrate` | advisory-locked; the **only** place migrations run |
| `web` | `gunicorn config.wsgi:application -c gunicorn.conf.py` | **gunicorn/WSGI** (not uvicorn); tuned in `gunicorn.conf.py` (workers=`cpu*2+1`, threads=2, timeout=60, `max_requests=1000`+jitter) |
| `celery-worker` | `celery -A config worker` | async AI jobs + side effects |
| `celery-beat` | `celery -A config beat` | scheduled tasks |
| `mysql` | mysql:8.0 | **replace with managed MySQL in prod** |
| `redis-broker` | redis:7 `--maxmemory-policy noeviction` | broker+results (/0) — must not evict |
| `redis-cache` | redis:7 `--maxmemory-policy allkeys-lru` | app cache (/1) + sessions (/2) — **separate instance** |
| `frontend` | nginx serving the built SPA + proxying `/api,/admin,/static,/healthz,...` to `web:8000` (`frontend/nginx.conf`) | static bundle |

**Recommended production shape:**
- **Frontend (SPA):** build (`frontend/`) and serve as static assets on a **CDN / static host** (CloudFront+S3,
  Cloudflare Pages, Netlify, **or Vercel — SPA only**). Point `/api` at the backend, OR keep the provided
  nginx container as the edge that both serves the SPA and reverse-proxies the API.
- **Backend + workers + broker:** a **container platform / managed container service** — ECS Fargate, GKE/EKS,
  Google Cloud Run (web) + a worker service, Render, Railway, or Fly.io. Run **web**, **celery-worker**,
  **celery-beat** as separate scalable services from the **one-shot migrate** job.
- **Data/infra (managed):** managed **MySQL 8** (+ replica), managed **Redis** (two logical roles: a
  **noeviction broker** and an **LRU cache** — ideally separate instances/clusters, as prod compose already
  splits them), and a **TLS-terminating load balancer / ingress** in front of `web` (ALB / Cloud LB / nginx
  ingress) — required because `prod.py` expects `X-Forwarded-Proto=https` and forces `SECURE_SSL_REDIRECT`.
- **Must run in prod (checklist):** ✅ web (gunicorn) · ✅ celery-worker · ✅ celery-beat · ✅ Redis broker
  (noeviction) · ✅ Redis cache/session (LRU) · ✅ MySQL (+ optional replica) · ✅ TLS/LB · ✅ the one-shot
  `migrate` job on each deploy · ✅ static/SPA host · (recommended) Flower behind auth, Sentry, a metrics
  scraper hitting `/metrics`.

---

## 4. What's still stubbed / not production-grade (honest list)
- **Email / SMTP — NOT wired (real gap for a public site).** No `EMAIL_*` config; allauth email
  verification is `"none"` (`base.py:311`). Password reset, email verification, and any email
  notification will not send. **Code work:** add an email backend + `EMAIL_*` env + wire allauth flows,
  and provision an SMTP/email provider (SES/SendGrid/Postmark). *(~1–2 days code + provisioning.)*
- **Dev bind-mount & dev settings — handled for prod.** `docker-compose.yml` uses `- .:/app` +
  `config.settings.dev`; **`docker-compose.prod.yml` bakes the image (no source mount) and runs
  `config.settings.prod`.** Just deploy with the prod compose/image — no code change.
- **LLM provider default is off.** `LLM_PROVIDER` defaults to `NotConfiguredProvider` (`base.py:414`) — agents
  return a clean 503 and **never fabricate** until a key is set. Production sets it to `OpenAIProvider`
  (`AI_GOLIVE.md`). Not a bug — an explicit safe default.
- **`LLM_MAX_CALLS=500` is a dev/QA value.** Must be sized to tenant count or set `0` + a provider-side
  dollar cap (`base.py:433–441`, `AI_GOLIVE.md:53–60`). Config, not code.
- **Integrations (Slack / Jira) — scaffolded, not connected.** `apps/integrations/secrets.py` resolves a
  token by env name and **no-ops cleanly if unset**; there is no live Slack/Jira delivery wired for real
  use. Label them "not connected" until built. **Code work if in scope** (~2–5 days each).
- **SSO / SAML — implemented, needs a real IdP.** OIDC + SAML 2.0 are built and tested against a **mock
  IdP** (`docs/SSO.md`). Going live needs each customer to provide a **real IdP** (Okta/Azure AD/…) and
  per-tenant SP registration. Provisioning + per-tenant config, minimal code.
- **⚠️ Identifiable-data egress to OpenAI — AWAITING SIGN-OFF.** `docs/AI_GOLIVE.md:31–51`: the Review/JD/
  Career agents send employee first name + KPI numbers/attainment/risk to OpenAI (a US processor); the
  gateway PII-scrub is **email-only**. Options: (A) accept OpenAI terms / sign a DPA, (B) per-tenant opt-in,
  (C) pseudonymise those 3 agents (~1–2 days code). **A product/legal decision — do not launch the human-read
  agents on real employee data without it.** (Feedback/Succession agents are already name-free.)
- **GDPR data export/delete — not built** (`SYSTEM_DESIGN §6`). Per-tenant data retention/export/erasure is
  a likely requirement for EU customers. **Code work** (~3–5 days).
- **No WAF/DDoS layer, no per-tenant rate limiting beyond AI throttles** (`SYSTEM_DESIGN §6`) — provision at
  the edge (Cloudflare/WAF).

---

## 5. Scale readiness (5k–15k users/tenant × many tenants)

**Already handled (verified in code):**
- **N+1 on list endpoints — fixed & regression-guarded.** `select_related`/`prefetch` + a query-budget guard
  (`docs/QUERY_BUDGETS.md`, `apps/testsupport/query_budget.py`, `apps/core/tests/test_query_budgets.py`): e.g.
  reviews 78→3, goals 103→4 queries; "every paginated list is O(1) in rows." A `-m large_tenant` test seeds
  ~1.2k employees and asserts a query ceiling. *(Contra the stale SYSTEM_DESIGN §3.2 "⚠ REAL" warning.)*
- **Heavy AI is OFF the request thread.** `enqueue_agent_job` creates a tenant-scoped `AIJob` and dispatches
  the Celery task `run_agent_job` (`apps/ai/services.py:17–33`, `apps/ai/tasks.py:123` `@shared_task`); the
  client polls the job. Only **chat/planner intent-classification** is a synchronous LLM call (AI-throttled +
  budgeted). *(Contra the stale SYSTEM_DESIGN §3.4 "AI is NOT offloaded".)*
- **Budget/throttle is atomic across replicas.** Redis Lua reserve with `EVALSHA` + fallback recovery and
  fail-open-on-Redis-down + a metric (`apps/billing/atomic.py`). *(Contra the stale "not atomic" claim.)*
- **Caching** with tenant-scoped keys, TTLs, and degrade-not-error (`docs/CACHING.md`, `base.py:207–228`
  `IGNORE_EXCEPTIONS=True`).
- **DB replica router** active + config-only to point at a real replica (§2).
- **Health/readiness/metrics** exist: `/healthz`, `/readyz` (DB primary + replica + cache + sessions + broker +
  migrations), token-gated Prometheus `/metrics` (`apps/core/urls.py:6–8`, `apps/core/views.py`,
  `docs/OBSERVABILITY.md`).

**Needs work / provisioning before real load:**
- **Managed MySQL sizing + connection pooler + replica** (§2) — the single-node compose MySQL (100 conns) is
  the first hard ceiling and a SPOF.
- **Celery worker autoscaling** — not automated; provision HPA / a managed autoscaler and separate queues if
  AI jobs and side-effects compete. *(Provision + minor config.)*
- **Monitoring/alerting stack** — the `/metrics` exporter + suggested SLIs/alert thresholds exist
  (`OBSERVABILITY.md:38–52`) but there is **no Prometheus/Grafana/alerting deployed** — provision it +
  wire Sentry (`SENTRY_DSN`). This is the biggest ops gap.
- **Redis HA** — provision managed Redis with failover for both broker and cache.
- **True $/token budget cap** — budgets are **call-count** proxies today; a spend-cap read from `TokenLedger`
  is a documented follow-up (`AI_GOLIVE.md`). Pair with a provider-side hard dollar cap now. *(~1–2 days code.)*
- **DB TLS in-app** (§2) and **edge WAF/rate-limiting** (§4).
- **Load test** at target concurrency before onboarding a 5k–15k-employee tenant (the docs' throughput
  numbers are "reasoning, not measured," `SYSTEM_DESIGN §8`).

---

## 6. Go-live checklist + effort + timeline

Legend: **[P]** = provision/procure (company provides) · **[C]** = code work (build). Effort is rough.

### A. Must-have before ANY real users (controlled pilot)
| Item | Type | Effort |
|---|---|---|
| Managed MySQL 8 + automated backups + **tested restore** | [P] | — |
| Managed Redis: broker (noeviction) + cache (LRU) | [P] | — |
| TLS-terminating load balancer / HTTPS ingress in front of `web` | [P] | — |
| Container host for web + celery-worker + celery-beat (not Vercel) | [P] | — |
| Static/SPA host or the nginx edge for the frontend | [P] | — |
| Generate + inject real `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, DB creds via the host secret store | [P] | — |
| Platform LLM key + **provider-side dollar cap**; set `LLM_MAX_CALLS` (or 0) | [P] | — |
| Deploy via `docker-compose.prod.yml` (baked image, run the one-shot `migrate`) | [P] | ~0 (already built) |
| **Wire email/SMTP** (backend + `EMAIL_*` + allauth reset/verify) + provider | [C]+[P] | 1–2 days |
| **Sign off OpenAI identifiable-data egress** (accept DPA, or pseudonymise 3 agents) | [P] decision (+[C] if option C) | 0–2 days |
| Rotate/scrub demo data; confirm per-tenant `AgentBudget` tiers | [C] small | 2–4 h |
| Point `/metrics` token + `SENTRY_DSN`; basic uptime check on `/readyz` | [P] | — |

### B. Needed before scale (many tenants / 5k–15k each)
| Item | Type | Effort |
|---|---|---|
| Provision + point at a real **read replica** (`DB_REPLICA_*`) | [P] | ~0 (config) |
| **Connection pooler** (ProxySQL/RDS Proxy) + MySQL sizing | [P] | — |
| **Monitoring stack** (Prometheus/Grafana scraping `/metrics`) + alerts on the documented SLIs | [P] (+[C] minor) | 0.5–1 day wiring |
| **Celery autoscaling** + separate queues (AI vs side-effects) | [P] (+[C] minor) | 0.5–1 day |
| Redis HA/failover | [P] | — |
| **True $/token budget dimension** from `TokenLedger` | [C] | 1–2 days |
| **DB TLS** in `OPTIONS` (or private-network guarantee) | [C] small / [P] | 1–3 h |
| Tenant-scale indexing/partitioning review on the biggest tables | [C] | 1–3 days |
| Edge **WAF / rate limiting** | [P] | — |
| **Load test** at target concurrency | [C]/[P] | 1–2 days |

### C. Nice-to-have
| Item | Type | Effort |
|---|---|---|
| Real Slack/Jira integrations (currently scaffolded) | [C] | 2–5 days each |
| **GDPR** data export/erasure per tenant | [C] | 3–5 days |
| Per-tenant LLM keys (only if a customer demands own billing/DPA) | [C] | 1–2 days |
| Real-LangGraph node runner swap; LangSmith tracing on | [C]/[P] | 1–2 days |
| Secrets **vault** (upgrade from env injection) via `resolve_secret` seam | [P] (+[C] small) | 0.5 day |
| A real per-customer IdP round-trip test (SSO) | [P] | — |

### Realistic timeline to production (assuming prompt provisioning)
- **Controlled pilot (single/few tenants, must-haves A):** **~1–2 weeks.** The code is largely ready; the
  critical path is provisioning (managed MySQL/Redis/TLS/host) running in parallel with the email wiring
  (~1–2 days) and the OpenAI-egress sign-off. Deploy is `docker-compose.prod.yml`.
- **Scale-ready (many tenants, 5k–15k each, set B):** **+2–4 weeks** on top (monitoring/alerting, pooler +
  replica + sizing, autoscaling, $-budget, indexing review, and a real load test). **Total ≈ 4–6 weeks.**
- **Nice-to-haves (set C)** are post-launch and can land incrementally.

---
*Grounded in: `config/settings/base.py`+`prod.py`+`dev.py`, `docker-compose.yml`+`docker-compose.prod.yml`,
`gunicorn.conf.py`, `requirements.txt`, `apps/core/{dbrouter.py,views.py,urls.py,management/commands/deploy_migrate.py}`,
`apps/billing/{atomic.py,models.py,packs.py}`, `apps/ai/{services.py,tasks.py,providers.py}`,
`apps/integrations/secrets.py`, and docs (`AI_GOLIVE`, `RUNBOOK`, `OBSERVABILITY`, `CACHING`, `QUERY_BUDGETS`,
`SSO`; the Jul-4 `SYSTEM_DESIGN_AND_READINESS`/`PROD_READINESS_STATUS` are stale where noted). Read-only — no code changed.*
