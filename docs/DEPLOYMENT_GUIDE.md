# DEPLOYMENT_GUIDE — Axiom PMS (self-contained)

Everything the deployment team needs to stand up Axiom in production, grounded in
the real code (`docker-compose.prod.yml`, `config/settings/prod.py`, `.env.example`).
No prior context required.

## 1. What the product is

Axiom is a multi-tenant, AI-assisted **Performance Management System** (goals/OKRs,
reviews, 360° feedback, check-ins, recognition, org chart, JD generator, analytics).
Backend = Django + DRF (gunicorn/WSGI); frontend = a React SPA served by nginx that
also reverse-proxies `/api` to the backend. Each customer is an isolated **tenant**;
JWTs carry `tenant_id` + role; every AI output is human-gated (HITL).

## 2. Services it needs (and WHY)

| Service | Required | Why |
|---|---|---|
| **web** (gunicorn) | ✅ | The Django API + serves the SPA via the nginx front. |
| **celery-worker** | ✅ | Runs AI jobs (review/feedback/JD/etc. drafts) **in the background**. |
| **celery-beat** | ✅ | Scheduled tasks (approval-escalation sweep, etc.). |
| **MySQL 8** | ✅ | Primary datastore (multi-tenant, `utf8mb4`, strict mode). |
| **Redis — broker** | ✅ | See below. `--maxmemory-policy noeviction`. |
| **Redis — cache/sessions** | ✅ | See below. `--maxmemory-policy allkeys-lru`. |
| **SMTP provider** | ✅ | Password reset, email verification, invitations, email-change. |
| TLS-terminating LB / ingress | ✅ | prod forces HTTPS (`SECURE_SSL_REDIRECT`, expects `X-Forwarded-Proto=https`). |

### Redis is REQUIRED — here's why (not optional)

AI calls (Gemini/OpenAI) take **10–16 s** and can spike or rate-limit. If they ran
inside the web request, a burst of AI actions would **tie up every gunicorn worker
and stall the whole app** under load. Axiom avoids this by running heavy AI in
**Celery**, and Celery needs a **broker** — that broker is **Redis**:

- **Redis #1 — broker (`noeviction`)**: the queue between the web tier and the
  Celery workers. `enqueue_agent_job` drops an `AIJob` on this queue and the web
  request returns immediately; a worker picks it up. `noeviction` is mandatory so
  a memory spike can never silently **drop a queued job**. Without this broker,
  there is no background AI at all — slow AI would block/crash the app.
- **Redis #2 — cache + sessions (`allkeys-lru`)**: tenant-scoped response cache,
  rate-limit counters (atomic cross-replica Lua), and device sessions. LRU is fine
  here (a cache miss just recomputes). Kept **separate** from the broker so cache
  churn can never evict a queued job.

Two logical Redis roles → two instances (or two clusters). This is a deliberate,
load-bearing part of the architecture, not a nicety.

## 3. Prerequisites

- Docker + Docker Compose (or a container platform: ECS/GKE/Cloud Run/Render/Fly).
- **MySQL 8** (managed recommended: RDS / Cloud SQL — with backups + tested restore).
- **Redis 7** — two instances (broker noeviction + cache LRU).
- An **SMTP** provider (SES / SendGrid / Postmark).
- A TLS-terminating load balancer / ingress in front of `web`.
- A platform **LLM key** (Gemini by default) + a provider-side dollar cap.

## 4. Every `.env` variable

Legend — **Req**: 🔴 must-set-or-it-won't-boot · 🟡 needed for full function · ⚪ optional/feature-gated (blank = off).

### Core / Django
| Var | What | Where to get it | Req | Example |
|---|---|---|---|---|
| `DJANGO_SETTINGS_MODULE` | Which settings | fixed | 🔴 | `config.settings.prod` |
| `DJANGO_SECRET_KEY` | Django + JWT signing key | generate 50+ random chars | 🔴 | `django-insecure-…(rotate!)` |
| `DJANGO_ALLOWED_HOSTS` | Host allow-list | your domain(s) | 🔴 | `app.acme.com,api.acme.com` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | CSRF origins (SPA) | your https origin(s) | 🟡 | `https://app.acme.com` |
| `DJANGO_DEBUG` | Debug (never true in prod) | fixed | 🟡 | `false` |
| `DJANGO_SECURE_SSL_REDIRECT` | Force HTTPS | fixed | 🟡 | `true` |
| `DJANGO_HSTS_SECONDS` | HSTS max-age | choose | ⚪ | `31536000` |
| `APP_NAME` | Product display name (emails) | your brand | ⚪ | `Axiom` |
| `LOG_LEVEL` | Log verbosity | choose | ⚪ | `INFO` |

### Database (MySQL)
| Var | What | Where | Req | Example |
|---|---|---|---|---|
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` | MySQL creds | your MySQL | 🔴 | `pms` / `pms` / `…` |
| `DB_HOST` / `DB_PORT` | MySQL address | your MySQL | 🔴 | `mysql` / `3306` |
| `DB_ROOT_PASSWORD` | root (only if MySQL runs in compose) | compose only | ⚪ | `…` |
| `DB_CONN_MAX_AGE` | Persistent conn seconds | default | ⚪ | `60` |
| `DB_SSL_CA` | CA path for DB TLS | your MySQL provider | 🟡 (prod) | `/certs/rds-ca.pem` |
| `DB_REPLICA_HOST/PORT/USER/PASSWORD` | Read replica DSN | optional replica | ⚪ | blank = use primary |

### Redis / Celery
| Var | What | Where | Req | Example |
|---|---|---|---|---|
| `CELERY_BROKER_URL` | Broker (Redis #1, noeviction, db 0) | your broker Redis | 🔴 | `redis://broker:6379/0` |
| `CELERY_RESULT_BACKEND` | Task results | same broker | 🔴 | `redis://broker:6379/0` |
| `REDIS_CACHE_URL` | App cache (Redis #2, LRU, db 1) | your cache Redis | 🔴 | `redis://cache:6379/1` |
| `REDIS_SESSION_URL` | Sessions (Redis #2, db 2) | your cache Redis | 🔴 | `redis://cache:6379/2` |
| `CELERY_TASK_ALWAYS_EAGER` | Run tasks inline (NEVER true in prod) | fixed | 🟡 | `false` |
| `APPROVALS_ESCALATION_INTERVAL_SECONDS` | Beat sweep interval | default | ⚪ | `300` |

### Email / SMTP
| Var | What | Where | Req | Example |
|---|---|---|---|---|
| `EMAIL_BACKEND` | Email backend | fixed for prod | 🔴 | `django.core.mail.backends.smtp.EmailBackend` |
| `EMAIL_HOST` / `EMAIL_PORT` | SMTP server | your provider | 🔴 | `smtp.sendgrid.net` / `587` |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | SMTP creds | your provider | 🔴 | `apikey` / `…` |
| `EMAIL_USE_TLS` | STARTTLS | fixed | 🟡 | `true` |
| `DEFAULT_FROM_EMAIL` | From name/address | your domain | 🟡 | `Axiom <no-reply@acme.com>` |
| `PUBLIC_APP_URL` | SPA base URL (for links in email) | your domain | 🔴 | `https://app.acme.com` |

### AI (LLM)
| Var | What | Where | Req | Example |
|---|---|---|---|---|
| `LLM_PROVIDER` | Provider class | fixed | 🟡 | `apps.ai.gemini_provider.GeminiProvider` |
| `GEMINI_API_KEY` | Gemini key | Google AI Studio | 🔴 (for AI) | `AIza…` |
| `LLM_MAX_CALLS` | Deployment-wide call ceiling (cost backstop) | set for prod | 🟡 | `20000` (or `0` + provider $-cap) |
| `LLM_TIMEOUT_SECONDS` / `LLM_READ_TIMEOUT` | Connect / read timeouts | defaults | ⚪ | `30` / `60` |
| `LLM_MAX_TOKENS` | Max output tokens | default | ⚪ | `4096` |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `GROQ_API_KEY` | Alt providers | if used | ⚪ | blank |
| `LANGSMITH_API_KEY` | LLM tracing | optional | ⚪ | blank |

*(No LLM key → AI endpoints return a clean 503 and never fabricate; the rest of the
app works. Set `GEMINI_API_KEY` to enable AI.)*

### Auth / throttling
| Var | What | Req | Example |
|---|---|---|---|
| `JWT_ACCESS_MINUTES` / `JWT_REFRESH_DAYS` | Token lifetimes | ⚪ | `15` / `7` |
| `LOGIN_LOCKOUT_ATTEMPTS` / `LOGIN_LOCKOUT_WINDOW_SECONDS` | Lockout | ⚪ | `8` / `900` |
| `THROTTLE_ANON` | Anon per-IP rate | ⚪ | `100/min` |
| `SIGNUP_DEFAULT_SEATS` | Seats for a new self-serve tenant | ⚪ | `5` |

### Observability
| Var | What | Req | Example |
|---|---|---|---|
| `METRICS_TOKEN` | Bearer to expose `GET /metrics` (fail-closed → 404 if unset) | 🔴 (for monitoring) | `long-random` |
| `SENTRY_DSN` / `SENTRY_ENVIRONMENT` / `SENTRY_TRACES_SAMPLE_RATE` | Error tracking | 🟡 | your Sentry DSN |
| `FLOWER_BASIC_AUTH` | Celery dashboard auth | 🟡 | `admin:strongpass` |

### Feature-gated (blank = OFF — safe to leave unset)
| Var | What | Req | Example |
|---|---|---|---|
| `PAYMENTS_ENABLED` | Turn on the payment gate | ⚪ | `false` (blank/false = off) |
| `STRIPE_SECRET_KEY` / `STRIPE_PUBLISHABLE_KEY` / `STRIPE_WEBHOOK_SECRET` | Stripe (TEST keys first) | ⚪ | blank = off |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` / `RAZORPAY_WEBHOOK_SECRET` | Razorpay (TEST first) | ⚪ | blank = off |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | Sign-in-with-Google | ⚪ | blank = off |
| `OIDC_*` | Enterprise OIDC SSO | ⚪ | blank = off |
| `MEDIA_ROOT` | Upload dir (avatars/logos) | 🟡 | `/app/media` (mount a volume) |
| `V1_HIDE_TSCORE` | UI flag | ⚪ | `true` |

## 5. Step-by-step deploy

```bash
# 1. Fill .env from .env.example (all 🔴 + 🟡 set; 🔴 or it won't boot).
cp .env.example .env && edit .env

# 2. Build the baked prod image.
docker compose -f docker-compose.prod.yml build

# 3. Start data services: MySQL + BOTH Redis instances.
docker compose -f docker-compose.prod.yml up -d mysql redis-broker redis-cache

# 4. Run migrations ONCE (advisory-locked; the ONLY place migrations run).
docker compose -f docker-compose.prod.yml run --rm migrate      # → python manage.py deploy_migrate

# 5. Start the app tiers.
docker compose -f docker-compose.prod.yml up -d web celery-worker celery-beat frontend

# 6. Healthcheck.
curl -fsS https://<your-domain>/healthz        # → 200
curl -fsS https://<your-domain>/readyz         # → 200 (DB + cache + sessions + broker + migrations)

# 7. Create the first real tenant + admin via the product (NOT a script):
#    open https://<your-domain>/signup → fill org name / your name / email / password
#    → you land in the Admin Hub as ADMIN of a fresh, isolated tenant.

# 8. Smoke test (see checklist below).
```

## 6. CLEAN DATA — production starts EMPTY

- A fresh prod DB comes up with **schema only** — **NO demo/mock data auto-loads.**
  `docker-compose.prod.yml` runs `deploy_migrate` (migrations) only; web/workers
  wait on it and never seed. No data migration inserts rows.
- **`seed_demo_rich` is for testing/demo ONLY — never run it in production.**
- Real data enters via **self-serve signup** (`/signup`) + **CSV import** /
  invitations (Admin → Users).

```bash
# Clean production DB (schema only, zero tenants):
docker compose -f docker-compose.prod.yml run --rm migrate

# Seed a DEMO/testing environment (NOT prod) — tenant 'acme', ~210 people:
docker compose exec web python manage.py seed_demo_rich
```

## 7. "Did it work?" checklist

- [ ] `/healthz` and `/readyz` both return **200**.
- [ ] `/signup` creates a workspace and logs you in as ADMIN.
- [ ] **Login** works; a wrong password is rejected.
- [ ] **One AI action** (request a review draft) resolves to a draft, or a clean
      "couldn't generate — retry" (never an infinite spinner). Watch it in Flower.
- [ ] **One email** arrives (trigger "forgot password"); check the inbox/SMTP logs.
- [ ] `GET /metrics` with `Authorization: Bearer $METRICS_TOKEN` returns metrics
      (and **404 without** the token).
- [ ] The tenant DB is otherwise **empty** (no ACME/mock data) unless you seeded a demo.

## 8. Troubleshooting

| Symptom | Cause → fix |
|---|---|
| Boot fails: `SECRET_KEY` / `ImproperlyConfigured` | `DJANGO_SECRET_KEY` unset → set it (prod fails closed). |
| `DisallowedHost` / 400 on every request | `DJANGO_ALLOWED_HOSTS` missing your domain → add it. |
| 500s, `OperationalError` to DB | DB creds/host wrong, or DB TLS required → check `DB_*`, set `DB_SSL_CA` (or private-network the DB). |
| AI actions never finish / jobs stuck QUEUED | Celery can't reach the **broker** → check `CELERY_BROKER_URL` reachable + worker running (`docker compose logs celery-worker`). |
| Cache/session errors, login not persisting | `REDIS_CACHE_URL` / `REDIS_SESSION_URL` unreachable → verify the cache Redis is up. |
| No emails (reset/invite) | `EMAIL_*` unset or wrong, or `PUBLIC_APP_URL` blank → configure SMTP; links use `PUBLIC_APP_URL`. |
| `/metrics` returns 404 | `METRICS_TOKEN` unset (fail-closed) → set it and send the Bearer. |
| Queued AI jobs vanish under load | broker Redis is evicting → it MUST be `--maxmemory-policy noeviction`. |

See also: `docs/DEPLOYMENT_HANDOVER.md`, `docs/DATA_HANDOVER.md`,
`docs/AI_ROBUSTNESS.md`, `docs/OBSERVABILITY.md`, `docs/RUNBOOK.md`.
