<h1 align="center">Axiom</h1>

<p align="center">
  <strong>A multi-tenant, AI-assisted Performance Management System for SMEs.</strong><br>
  Goals &amp; OKRs · Reviews · 360° Feedback · Check-ins · Recognition · Org Chart · JD Generator · Analytics
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white" alt="Python 3.11">
  <img src="https://img.shields.io/badge/Django-4.2-092E20?logo=django&logoColor=white" alt="Django 4.2">
  <img src="https://img.shields.io/badge/MySQL-8-4479A1?logo=mysql&logoColor=white" alt="MySQL 8">
  <img src="https://img.shields.io/badge/Redis%20%2B%20Celery-async-DC382D?logo=redis&logoColor=white" alt="Redis + Celery">
  <img src="https://img.shields.io/badge/React%20%2B%20TS-SPA-3178C6?logo=react&logoColor=white" alt="React + TypeScript">
  <img src="https://img.shields.io/badge/LLM-provider--agnostic%20(Gemini)-3ee8c5" alt="Provider-agnostic LLM">
</p>

---

## What Axiom is

Axiom runs the full performance cycle for a company — **goals/OKRs, reviews, 360°
feedback, weekly check-ins, recognition, a live org chart, an AI JD generator, and
analytics** — with AI woven through every surface under one operating rule:

> **The AI proposes. A human always approves.**

Every AI output (a review draft, a 360 summary, a generated JD, a multi-step plan)
is produced from **real tenant data only**, lands in a `PENDING_HUMAN_REVIEW` state
behind a hard human-in-the-loop (HITL) gate, is checked against RBAC, and is recorded
in an append-only audit log. Each customer is an isolated **tenant**.

## Tech stack

| Layer | Choice |
|---|---|
| Backend | **Python 3.11 · Django 4.2 · Django REST Framework** (gunicorn/WSGI) |
| Database | **MySQL 8** (multi-tenant, `utf8mb4`, strict mode) |
| Async / queue | **Redis 7 + Celery** — heavy AI runs off the request thread |
| Frontend | **React + TypeScript + Tailwind + shadcn/ui** (SPA served by nginx) |
| AI | **Provider-agnostic LLM gateway** (defaults to **Google Gemini**; OpenAI/Groq pluggable) |
| Auth | JWT (simplejwt) + OAuth/OIDC (allauth) + SAML 2.0 + MFA (TOTP); Argon2 passwords |

## Quickstart (local demo)

```bash
# 1. Bring the stack up (web + celery worker/beat + MySQL + Redis + frontend).
docker compose up -d

# 2. Run migrations (advisory-locked; the only place migrations run).
docker compose run --rm web python manage.py deploy_migrate

# 3. Seed the rich demo tenant (~210 people across every module; idempotent).
docker compose exec web python manage.py seed_demo_rich

# 4. Open the app.
open http://localhost:8090
```

**Demo accounts** — tenant **`acme`**, password **`Passw0rd!demo`**:

| Login | Role | Sees |
|---|---|---|
| `admin@acme.test` | ADMIN | whole tenant |
| `priya@acme.test` | HRBP | business unit |
| `ada@acme.test` | MANAGER | own + team |
| `akhil@acme.test` | EMPLOYEE | own data |

One-command full check: `./scripts/qa_handover.sh` (reseeds, seeds the `globex`
cross-tenant fixture, runs 131 API checks). Backend tests: `docker compose exec web pytest`.

## Key features

- **Goals & OKRs** — weighted goals + KPIs, cycle scoring, progress timelines.
- **Reviews** — HITL state machine (draft → pending → approved → finalized), AI drafts.
- **360° Feedback** — anonymized, request/response cycles, AI summaries.
- **Check-ins & Recognition** — weekly notes + a kudos feed.
- **Org chart, JD generator, Analytics** — live reporting tree, AI JDs, cohort analytics.
- **Onboarding** — self-serve tenant signup, CSV bulk employee import, invitations.
- **Billing** — plans + a payment gate (Stripe + Razorpay, **test mode**).
- **AI assistant** — a propose-confirm agent that only ever executes registered,
  RBAC-checked, human-approved actions.

## Architecture principles (non-negotiable)

- **Tenant isolation** — every model is tenant-scoped with a fail-closed manager; a
  cross-tenant id returns 404, never a leak. JWTs embed `tenant_id` + role.
- **Server-side RBAC** — enforced on every endpoint (4 roles: Employee < Manager <
  HRBP < Admin). The SPA never gates; the server is the sole authority.
- **HITL on all AI** — every AI output is saved `PENDING_HUMAN_REVIEW`; nothing is
  published or written without explicit human approval. AI never fabricates on failure.
- **INSERT-only audit log** — consequential actions are recorded immutably (no update,
  no delete at the DB level).
- **AI off the request thread** — heavy AI runs in **Celery** (Redis broker), so a
  slow/failing model call can never block or crash the web tier under load.

## Documentation

| Doc | For |
|---|---|
| [`docs/DEPLOYMENT_GUIDE.md`](docs/DEPLOYMENT_GUIDE.md) | Deployment team — services, every env var, step-by-step deploy, troubleshooting |
| [`docs/TESTING_GUIDE.md`](docs/TESTING_GUIDE.md) | Testing team — demo accounts, what to test, what's covered, bug-report format |
| [`docs/SECURITY_TESTING_HANDOVER.md`](docs/SECURITY_TESTING_HANDOVER.md) | Security testers — surfaces worth attention, staged items |
| [`docs/DATA_CLEANUP.md`](docs/DATA_CLEANUP.md) | Demo-data hygiene + per-module verification |
| [`docs/DATA_HANDOVER.md`](docs/DATA_HANDOVER.md) | Mock vs real data; clean empty prod vs demo seed |
| [`docs/PROD_READY_REPORT.md`](docs/PROD_READY_REPORT.md) | Production-readiness summary + morning checklist |
| [`docs/AI_ROBUSTNESS.md`](docs/AI_ROBUSTNESS.md) · [`docs/SSO.md`](docs/SSO.md) · [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | AI under load · SSO · ops runbook |

## Data: production starts empty

A fresh production deploy comes up with an **empty database** — migrations only, **no
mock data auto-loads**. `seed_demo_rich` is for testing/demo **only** and is never run
in production. Real data enters via self-serve signup + CSV import. Details in
[`docs/DATA_HANDOVER.md`](docs/DATA_HANDOVER.md).

## Staged / not yet live (honest status)

- **Payments** are built and verified in **TEST MODE** (signature-verified webhooks,
  idempotent, tenant-isolated). Live keys + the provider `create_checkout` SDK call
  are a supervised go-live step. Off by default (`PAYMENTS_ENABLED=false`).
- **Sign-in with Google / enterprise SSO** is wired (allauth OIDC + SAML, no-JIT) but
  needs the customer's real OAuth creds / IdP to exercise end to end.
- **Mobile app** is deferred to **v2** — the web app is responsive.
- **Email** uses the console backend in dev; production needs a real SMTP provider.

## Configuration

All configuration is via environment variables — see **`.env.example`** for the full
list with comments. Never commit a filled `.env` (it is gitignored); production
injects secrets via the platform secret store.
