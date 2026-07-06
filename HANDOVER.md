# HANDOVER — Talbotiq PMS (plain-English guide for the next developer)

This document explains, in simple terms, **what this project is, what it does, how it's
built, how to run it, and what's left to do** — so you can pick it up without anyone
explaining it to you. No prior context needed.

> **Read first (current state, July 2026):** the fastest way to run everything is one command —
> `./scripts/demo_ready.sh` (§5). The branch you're likely on, `hari/agent-ui-v2`, is the demo
> build (main + the V3 agentic-chat/plan UI); the branch model and known caveats are in **§11**.

---

## 1. What this project is

**Talbotiq PMS** is an **AI-assisted Performance Management System** for small/medium
companies. It's the software HR teams and managers use to run performance cycles: set
goals, track KPIs, write and approve reviews, collect 360° feedback, plan succession,
generate job descriptions, and see analytics — with AI helping draft text and a strict
"a human always approves" rule.

It is **multi-tenant**: one running system serves many separate companies ("tenants"),
and one company can **never** see another company's data.

There are two parts:
- a **web app** (the "Admin Hub") for managers, HR, and admins — this is the main, finished product;
- a **mobile app** (Expo/React Native) for employees — this is **partially built and paused** (see §9).

---

## 2. How it's built (the tech)

| Layer | Technology |
|---|---|
| Backend | Python 3.11, Django 4.2, Django REST Framework |
| Database | MySQL 8 |
| Cache, sessions, background jobs | Redis 7 + Celery (workers + a scheduler called "beat") |
| AI | An "LLM Gateway" + provider classes (currently **OpenAI**; Groq also available) |
| Frontend (web) | React + TypeScript + Vite + Tailwind CSS + shadcn/ui components |
| Mobile (paused) | Expo SDK 54 + React Native + NativeWind |
| Login & security | JWT tokens, OAuth/OIDC login, SAML 2.0 single sign-on, MFA (one-time codes), Argon2 passwords |
| Runs via | Docker Compose (everything is containers) |

Everything runs locally with **Docker Compose** — you don't install Python/MySQL by hand.

---

## 3. The features (each one, in plain English)

The backend is split into "apps" (folders under `apps/`). Here's what each does:

**Foundations**
- **tenancy** — the multi-company engine. Every record belongs to a tenant, and the
  system automatically filters every database query by the logged-in user's tenant. If
  no tenant is set, it returns nothing (it "fails closed" — safe by default).
- **identity** — users, login, JWT tokens, MFA (authenticator-app codes), OIDC/OAuth
  login, and **SAML 2.0 single sign-on** (a company can plug in Okta/Azure AD).
- **rbac** — role-based access control. Four roles: **Employee** (own data), **Manager**
  (their team), **HRBP** (their business unit), **Admin** (the whole company). Every
  endpoint checks the role on the server.
- **audit** — an append-only log of every important action. Records can be inserted but
  **never edited or deleted** (enforced at the database level) — a tamper-proof trail.

**Performance management**
- **cycles** — performance review periods (e.g. "H1 2026") and the scoring engine that
  turns goals + KPI results into a score per employee.
- **goals** — goals and KPIs. A key rule: an employee's active goal weights, and a goal's
  KPI weights, must each add up to **exactly 100.00**. Managers approve goals.
- **reviews** — performance reviews with a strict state machine
  (Draft → AI Drafting → Pending Human Review → Approved → Finalized). A review can
  **never be finalized without a human approving it** (the "HITL" rule — Human In The Loop).
- **feedback** — 360° feedback. Feedback is **anonymised** before it's shown, with a
  minimum-group-size rule so individuals can't be identified.
- **approvals** — multi-step approval workflows (sequential or parallel approvers) with
  automatic **escalation**: if an approver doesn't act in time, it's reassigned.

**People & planning**
- **org** — the live org chart, positions, and vacancies.
- **succession** — succession planning, including a "nine-box" talent grid. Succession
  data is **name-free** where it matters (it talks about bench positions, not individuals).
- **career** — development roadmaps toward a target role.
- **jd** — AI job-description generator + a JD library.

**AI**
- **ai** — the **LLM Gateway**: the single place every AI call goes through. On every
  call it: checks the tenant's budget → removes personal info from the prompt → calls the
  AI provider → checks the answer matches the expected shape → records token usage →
  attaches a confidence score → saves the output as "Pending" for a human to approve.
  There are 5 AI agents (review draft, KPI nudges, feedback summary, succession narrative,
  career roadmap) plus a **read-only chat assistant**.

**Business & ops**
- **billing** — feature packs (STARTER vs FULL_AI), seat counts, per-tenant AI budgets.
- **integrations** — Slack notifications and a Jira seam (best-effort, never block the app).
- **analytics** — dashboards and calibration views (with the same scope rules).
- **administration** — tenant/user admin and KPI configuration.
- **core** — shared utilities, health checks, the demo-data seeder, error handling.

**On the web app** these show up as screens (folders under `frontend/src/features/`):
dashboard, goals, reviews, feedback, approvals, org chart, succession, analytics, JD,
career, audit, admin, plus a ⌘K command palette and the AI chat panel.

---

## 4. The safety rules (these must never be broken)

These are the project's non-negotiable rules. If you change code, keep all of these true:

1. **Tenant isolation** — every data model is tenant-scoped; one company can't see another's data.
2. **Server-side RBAC** — never trust the frontend; the server checks the role on every request.
3. **HITL (Human In The Loop)** — every AI output is saved as "Pending Human Review"; a
   human must approve it. A review can't be finalized without a recorded human approver.
4. **Audit log is insert-only** — no updates, no deletes, ever (enforced in the database).
5. **All AI calls go through the LLM Gateway** — never call an AI SDK directly.
6. **AI degrades gracefully** — no API key → the AI returns a clean "503 unavailable",
   never a fake answer; over-budget → "429 too many requests".

---

## 5. How to run it

You need **Docker** installed. From the project folder:

```bash
docker compose up -d            # start everything (MySQL, Redis, backend, frontend, workers)
./scripts/demo_ready.sh         # migrate + seed the rich demo + end-to-end smoke → "✓ DEMO READY"
```

`demo_ready.sh` is the one-command path: it recreates the backend on fresh code, runs
`seed_demo_rich` (the plentiful ACME demo), waits for health, and runs the full smoke. If you'd
rather do it by hand: `docker compose exec web python manage.py migrate` then
`docker compose run --rm web python manage.py seed_demo_rich`.

Then open the app:
- **Web app:** http://localhost:8080
- **Flower (background-job dashboard):** http://localhost:5555
- (MySQL is on localhost:3307, Redis on localhost:6380 — you rarely touch these directly.)

**Demo logins** (tenant `acme`, password `Passw0rd!demo`):

| Role | Email |
|---|---|
| Admin | `admin@acme.test` |
| HRBP | `priya@acme.test` |
| Manager | `ada@acme.test` |
| Employee | `akhil@acme.test` |

**Important operational note (two different reload behaviours):**
- **Backend** (`web`, `celery-worker`) is **bind-mounted** to the repo but runs gunicorn/celery
  **without auto-reload** — after changing backend code, restart: `docker compose restart web celery-worker`.
- **Frontend** (`frontend`) is a **built image**, not a live mount — after changing frontend code
  you must **rebuild it**: `docker compose up -d --build frontend`. (This matters: a green
  `demo_ready.sh` tests the API, not the browser bundle.)

---

## 6. How to test it

```bash
# Backend tests (run inside the container):
docker compose run --rm web pytest -q
#   → full suite green; a few heavy/live-AI tests are deselected on purpose

# Frontend tests / type-check / lint / build (from the frontend/ folder):
cd frontend
npm test            # vitest — green (includes accessibility + contrast guards)
npx tsc --noEmit    # type-check (clean)
npm run lint        # eslint (clean)
npm run build       # production build (clean)

# End-to-end smoke test over real HTTP (as each role):
docker compose exec web python scripts/smoke.py
```

Tests **never call a real AI provider** — they use a built-in `FakeLLMProvider` that
returns deterministic answers, so the test suite is fast and costs nothing.

---

## 7. The AI setup (current)

- The active AI provider is **OpenAI** (set in `docker-compose.yml` via `LLM_PROVIDER`).
- Models: **`gpt-4o`** for the "human-read" agents (review, feedback, succession, JD,
  career) and **`gpt-4o-mini`** for chat + default (cheaper/faster). These are easy to
  change in `config/settings/base.py` (`LLM_MODEL_MAP`) or via env vars.
- The API key lives in the **`.env`** file as `OPENAI_API_KEY` (this file is **never**
  committed to git). Without a key, all AI features return a clean "unavailable" message.
- **Cost guard:** OpenAI is paid per use, so there's a deployment-wide cap
  (`LLM_MAX_CALLS`, default **500**, cache-counted across web + workers) plus per-tenant budgets.
  A runaway loop can't burn the bill.
- **Switching providers** is config-only (no code rewrite). To go back to Groq: set
  `LLM_PROVIDER=apps.ai.groq.GroqProvider` + `GROQ_API_KEY` in `.env`. Full steps are in
  **`docs/AI_GOLIVE.md`**.

---

## 8. Where to find things (the docs that matter)

The repo has a lot of historical build notes; these are the ones worth reading:

| Read this | For |
|---|---|
| `CLAUDE.md` | the project's rules, stack, and build order (the "constitution") |
| `docs/PRODUCT_STATE.md` | the full as-built state of every feature |
| `docs/SYSTEM_DESIGN_AND_READINESS.md` | architecture + readiness |
| `docs/RUNBOOK.md` | operating the system (deploy, ops) |
| `docs/AI_GOLIVE.md` | the AI setup, models, budgets, switching providers |
| `docs/SSO.md` | single sign-on (OIDC + SAML) setup per company |
| `docs/ACCESSIBILITY.md` | the WCAG 2.1 AA accessibility work + what's automated vs manual |
| `docs/FUNCTIONAL_TEST_MATRIX.md` | which tests prove which behaviours |
| `PROGRESS.md` | a dated log of everything built (newest at top) |
| `DECISIONS.md` | **why** key choices were made (D1–D30) — read this to understand intent |
| `QUESTIONS.md` | open questions + the safe default taken for each |
| `BUGFIX_REPORT.md` | the most recent round of bug fixes |

Folders: backend code is in `apps/<feature>/`, web app in `frontend/src/`, mobile in
`mobile/`, infra in `docker-compose.yml` + `Dockerfile`.

---

## 9. Current status — what's done, what's pending

**Done and verified (web app):**
- All core modules above are built, tested (1209 backend + 76 frontend tests), and run.
- **SSO**: OIDC/OAuth proven; SAML 2.0 added and proven against a mock identity provider.
- **Accessibility**: WCAG 2.1 AA automated pass is clean on the key screens, with a guard test.
- **Functional test matrix**: review transitions, KPI=100% rule, approval escalations, and notifications are all test-backed.
- **Recent bug fixes** (all fixed + tested + verified live): goals "Approve" now updates the screen; the "Request AI Draft" action is reachable; the employee Career Roadmap link works (read-only); the AI chat assistant now understands different question types instead of always returning metrics.
- **AI provider** switched from Groq to **OpenAI** (config + a small provider class).

**Pending — needs a person / external setup (not code bugs):**
1. **OpenAI live test** — one real AI call to confirm end-to-end wiring. Waiting for the
   `OPENAI_API_KEY` to be put in `.env`. (Code is ready; tests pass with the fake provider.)
2. **A real production identity provider** (Okta/Azure AD) for live SSO — the customer provides it.
3. **Infrastructure security**: TLS (HTTPS) and AES-256 encryption-at-rest are server/DB
   configuration, not app code.
4. **Third-party penetration test** — an external vendor.
5. **User manuals** (a <2-hour training guide + technical docs) — a written deliverable.
6. **WCAG full certification** — automated checks pass; a manual/assistive-technology pass
   is still needed before claiming full certification (see `docs/ACCESSIBILITY.md`).
7. **Mobile app** — the foundation is built (Expo SDK 54, login, shell) but the screens
   are paused. See `MOBILE_MOCK_ADAPTATION.md` and `COE/MOBILE_BUILD_COE.md` for the plan.
   The one clear missing backend piece is **1:1 Meeting Notes**.

---

## 10. Suggested first steps for the new developer

1. Read `CLAUDE.md` and `DECISIONS.md` (understand the rules and the "why").
2. Run it: `docker compose up -d` → migrate → seed_demo → open http://localhost:8080 and log in as each role.
3. Run the tests (`pytest` and `npm test`) to see green.
4. Skim `docs/PRODUCT_STATE.md` for the feature-by-feature state.
5. When ready to turn the AI on, put `OPENAI_API_KEY` in `.env`, restart `web`, and do one
   small test (see `docs/AI_GOLIVE.md`).

If anything seems off, the dated build log and `*_REPORT.md` files in **`docs/archive/`** explain
how each piece was built and verified.

---

## 11. Current branch model, the demo, and known caveats (July 2026)

**Branches**
- **`main`** — the canonical backend + all merged work. This is the default branch.
- **`hari/agent-ui-v2`** — a review branch = `main` + the **V3 agentic-chat UI** (a multi-step
  plan panel with per-step Approve / "Approve all & run", plus the goal Updates timeline). This is
  the **demo build**. It has *not* been merged to main (the V3 frontend was never pixel-signed-off).
  If you're demoing the agentic chat, run the **frontend from this branch** (`docker compose up -d
  --build frontend` while checked out here).

**The two AI demos that work end-to-end today**
1. **Agentic chat** — as `ada@acme.test`, open the AI assistant → type
   *"start a 360 for Vera and draft her review"* → you get a **2-step plan** (both steps
   confirm-execute) → **Approve all & run** → a 360 cycle is created and an AI review draft is
   requested, both landing pending your approval. (This needs Vera in the seed — re-run
   `seed_demo_rich` if she's missing.)
2. **JD generation** — as `priya@acme.test` (HRBP): **JD Library → New JD** → open it →
   **Generate with AI** → give a one-line brief → the AI writes the JD → it lands
   `PENDING_HUMAN_REVIEW` → **Approve** to publish. (Ada/Manager can view the library but can't
   generate — JD authoring is HRBP+.) Full click-path in `DEMO_VIDEO_SCRIPT.md`.

**Known caveats (none are code bugs — good to know before a demo)**
- The **agentic plan panel + "Approve all & run"** lives only on `hari/agent-ui-v2`, not `main`.
  A green `demo_ready.sh` exercises the plan flow at the **API** level, not the browser — so for a
  screen demo, build the frontend from this branch and click through it yourself.
- A **persisted demo DB** (one that has survived many seed runs) can show **duplicate KPIs** per
  goal and stale 360 cycles. For a pristine recording, reset first:
  `docker compose down -v && docker compose up -d`, then `demo_ready.sh` (this wipes local demo
  data only — the DB is regenerable from the seed).
- **Live AI** uses `gpt-4o`/`gpt-4o-mini` via OpenAI; confirm the key has credit, or set
  `LLM_PROVIDER=apps.ai.providers.FakeLLMProvider` in `.env` for a deterministic, zero-spend run.
