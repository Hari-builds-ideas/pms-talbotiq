# PHASE4_MORNING_REPORT.md

**Run:** Autonomous Phase 4 — deepen the PMS into something a company would actually use.
**Model:** Claude Opus (did not switch).
**Starting point:** Phases 1–3 done/pushed/live (one Docker stack, frontend on the real API
with seeded data, AI agents alive on Groq through the safety pipeline).
**Outcome:** Five Phase-4 sub-phases delivered, each committed **and pushed** to `origin/main`,
product still running. **Both named AI-UX gaps fixed.** Stopped before 4d to keep a deep,
working, verified subset rather than start a large new surface I might not finish cleanly.

> Verification honesty: items marked **[live]** were exercised over real HTTP against the
> running stack and the result captured; **[build]** = verified by tsc/lint/build only.

---

## Sub-phases completed

### 4a — Role-true cockpit dashboards ✅ (`bfffa5b`)
Each role lands on its own work, composed client-side from real endpoints with real
counts/links/empty states:
- **Manager:** at-risk KPI nudges (real Agent-2), reviews to action, approval inbox, coverage gaps.
- **HRBP:** feedback summaries to release, succession coverage, approvals, at-risk people.
- **Admin:** tenant health (users by role), plan/seats, recent audit activity.
- **Employee:** own goals+KPIs, review status, feedback requests awaiting, career roadmap,
  and own T-score/risk (derived via `scores/me`, since employees can't list cycles).
Extended the typed API client with goals/feedback/career/cycle-scores groups + domain types.
**[live]** verified data per role (manager nudges/reviews, HRBP summaries/succession, admin
users/audit, employee goals/score).

### 4b — Review cycle as a guided workflow ✅ (`e9ef54c`)
The review detail is now guided, not just a state machine:
- **Evidence panel beside the draft:** the subject's goals + KPI attainment and their computed
  CycleScore (T-score/raw/cohort/pace + risk badge) — the manager and the AI draft work grounded
  in real data.
- **Assessment capture:** reviewer records a MANAGER assessment, subject a SELF assessment (one
  per assessor; SELF upserts, others create-once — the UI gates the form to match).
- Existing stepper, AI-draft, edit/submit, approve/reject(reason), finalize, linked approval-route
  tracker and transition timeline make every HITL gate obvious.
**[live]** manager assessment create → 201; team goals + scores reads scoped correctly.

### 4c — Goals & KPIs as a living surface ✅ (`9a55087`)
New **Goals & KPIs** screen (Manager+, nav-linked): goals grouped by employee with their risk
badge + T-score; a **weighted goal editor with a LIVE KPI-weight sum** (must equal 100, enforced
server-side); **record actuals** (own-only per `update_own_actuals`), **manager Approve**, and a
**Recompute scores** action that refreshes risk badges. Employees record their own actuals inline
from the cockpit.
**[live]** nested-KPI create → 201 (kpi_weight_total 100), recompute → 200, approve → 200,
employee own-actual → 201, HRBP-for-other → 403 (RBAC intact).

### 4e — Succession enrich switches to the new AI plan ✅ (`6bcb19c`) — **named gap #1 fixed**
Succession **Enrich (Agent 4)** creates a NEW `source=AI` plan (deterministic plan untouched);
the endpoint returns its `plan_id` and the panel now switches to that new AI plan so the real
Groq narrative is reviewed in its own HITL gate (PENDING → publish). Interactive nine-box,
bench/readiness and generate→review→publish already existed; this closes the Agent-4 loop.
**[live]** generate → 201, enrich → 200 returning a distinct `plan_id`; real Groq narrative on the
AI plan (Phase 3 transcript).

### 4f — JD AI-generate inputs form ✅ (`9ede57d`) — **named gap #2 fixed**
JD **"Generate with AI"** now opens a brief dialog (role summary + key responsibilities +
must-haves), saves it as the JD's generation inputs, THEN calls the generator — so it no longer
422s on missing inputs. The real Groq draft lands as a `source=AI` PENDING version reviewed before
publish.
**[live]** generate without inputs → 422; save brief → generate → 200, `source=AI`, PENDING, with a
draft body reflecting the brief.

(Org chart, analytics with min-cohort suppression, and integrations config were delivered in the
earlier frontend build and remain wired to the real API.)

---

## What is genuinely working end-to-end now
- Role-specific dashboards driving the work for all four roles (real counts/links/empty states).
- A manager can run a review grounded in real evidence (goals/KPIs/score) with self/peer
  assessments, request a **real Groq AI draft**, edit, approve and finalize — every HITL gate visible.
- A cycle can actually be run: weighted goals with a live 100% sum, KPI actuals recorded (own-only),
  scores recomputed, risk badges updated, goals approved.
- Succession: generate a deterministic plan → **enrich with real Agent-4** → review the AI plan in
  its HITL gate → publish; nine-box + bench all interactive.
- JD: author/lifecycle + **real AI generation** behind a proper inputs brief, locked PENDING.
- Chat: real, RBAC-scoped, read-only answers; write intents blocked.
All RBAC/scope/tenant isolation intact; succession invisible to employees; AI output real, metered,
PENDING_HUMAN_REVIEW.

## Groq usage this run (free-tier headroom)
- **15 real LLM calls total**, ~4,104 tokens metered in the `TokenLedger`:
  - `llama-3.3-70b-versatile` ×9 — Agent 1 (review), Agent 4 (succession ×7 across enrich tests),
    JD generator.
  - `llama-3.1-8b-instant` ×6 — Chat.
- Global run-ceiling counter at **15 / 60**. Well under 30 RPM, 1,000 RPD, 12,000 TPM.

## Commit + push list (this run)
- `bfffa5b` Phase 4a — role-true cockpit dashboards
- `e9ef54c` Phase 4b — review cycle as a guided workflow
- `9a55087` Phase 4c — goals & KPIs living surface
- `6bcb19c` Phase 4e — succession enrich switches to the new AI plan (named gap #1)
- `9ede57d` Phase 4f — JD AI-generate inputs form (named gap #2)
- (this commit) Phase 4 — morning report

## NEEDS_HARI / BLOCKER
- None new. No blockers hit; every push fast-forwarded.

## How to run
```bash
docker compose up -d --build                                   # full stack
docker compose run --rm web python manage.py seed_demo         # idempotent demo data
# http://localhost:8080 — tenant "acme", admin@acme.test / Passw0rd!demo (try each role)
docker compose run --rm web pytest -q                          # backend suite
```

## What remains / recommended next steps
1. **4d — 360 feedback end-to-end (not started):** request → give (anonymity/min-volume visible) →
   HRBP review/release of the real-AI summary (Agent 3) → subject's released view. The cockpit
   already surfaces "summaries to release"; this needs a dedicated feedback surface + closing/
   summarizing a cycle to produce the Agent-3 summary. Largest remaining piece.
2. **4g — cross-cutting polish (partial/not started):** global search, a notifications/inbox
   affordance, breadcrumbs, broader keyboard/responsive passes, a first-run/empty experience.
   (The AI chat is already genuinely useful and RBAC-scoped.)
3. The **mobile-web self-service surface** (separate build) for employees.
4. A **visual polish pass** + a **QA sweep** before handoff.

Tree clean; everything committed and pushed; stack running (`/` 200, `/readyz` 200). Backend suite
was last green at 1050 passed; Phase 4 changes were frontend-only (no backend code touched), so the
suite is unaffected.
