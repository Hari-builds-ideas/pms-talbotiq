# TalbotIQ PMS — Handoff (start here)

You've inherited this codebase. This folder is the complete handoff: what it is, how it works, what's
in v1 vs v2, how to run it, how it's deployed, and the open questions. Everything here is grounded in the
actual code — file paths and commands are real.

## What it is
**TalbotIQ PMS** — an AI-assisted, multi-tenant Performance Management System for SMEs (small/medium
companies). One running system serves many companies ("tenants"); one company can never see another's
data. It runs the performance cycle — goals & KPIs, reviews, 360° feedback, approvals, analytics — with
AI woven through every surface behind a hard **human-in-the-loop** gate: the AI proposes, a human always
approves. It is deliberately **simple** for non-expert users (v1 hides the enterprise-heavy features).

## Who it's for
Managers, HR business partners (HRBP), and admins at SMEs — non-technical users. The design test for
every screen: *"a manager understands it in ten seconds without training."*

## Tech stack (locked — see `CLAUDE.md`)
- **Backend:** Python 3.11 · Django 4.2 · Django REST Framework · MySQL 8 · Redis 7 + Celery
- **AI:** a provider-agnostic LLM gateway (OpenAI / Groq / **Gemini**) — one choke point, budgeted, HITL
- **Frontend:** React + TypeScript + Vite + Tailwind + shadcn/ui (a `shared/` TS package feeds web + mobile)
- **Auth:** JWT (simplejwt) + OAuth/OIDC + SAML 2.0 SSO + MFA (TOTP) + Argon2
- **Runs on:** Docker Compose (dev) / a baked image (prod)

## The other handoff docs (read in this order)
1. **`SYSTEM_OVERVIEW.md`** — every feature, the architecture, the request flow, and the invariants you
   must NOT break.
2. **`V1_VS_V2.md`** — the scope split: what's live, what's simplified, what's deferred-and-hidden, and
   **exactly how to re-enable** the hidden features. *The most important doc if you're continuing.*
3. **`HOW_IT_WAS_BUILT.md`** — the key decisions + why, and the testing approach.
4. **`DEVELOPER_SETUP.md`** — clone → run → seed → log in → test, in under an hour.
5. **`DEPLOYMENT.md`** — the free demo (Vercel + Render + Gemini) and the honest path to production.
6. **`MOBILE.md`** — mobile is **deferred to v2**: backend-ready, frontend needs work. Where to start.
7. **`OPEN_QUESTIONS.md`** — product decisions + known rough edges that aren't code, so they aren't lost.

## The 60-second orientation
- Backend apps live in `apps/<feature>/` (e.g. `apps/ai`, `apps/goals`, `apps/reviews`).
- The AI is `apps/ai/` — **all** LLM calls go through `apps/ai/gateway.py`; agents are in
  `apps/ai/agents/`; the plan→approve agent is `apps/ai/planner.py` + `apps/ai/actions.py`.
- The web app is `frontend/src/` (features in `frontend/src/features/<x>/`).
- v1 scope cuts are one file: **`frontend/src/app/v1.ts`**.
- Run it: `docker compose up -d` → `./scripts/demo_ready.sh`. Details in `DEVELOPER_SETUP.md`.
