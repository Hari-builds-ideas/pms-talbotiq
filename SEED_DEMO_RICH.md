# SEED_DEMO_RICH — plentiful, realistic demo data for ACME

A new idempotent management command that scales tenant **ACME (FULL_AI)** up to a real-sized,
believable dataset so every screen with a real data source looks full — **without fabricating** data
for features that have no source (the N6 / real-data rule).

## The one command to run

```bash
docker compose run --rm web python manage.py seed_demo_rich
```

Idempotent + deterministic — safe to re-run any number of times (it reuses rows on natural keys and
re-normalises weights/scores; it never duplicates). **ACME-only** — it does not touch `globex` and
does not break the base `seed_demo`. No live AI during seeding (scores are the deterministic engine;
360 summaries are left for the AI/HITL step — sections are never fabricated).

Demo login (unchanged): any seeded email + **`Passw0rd!demo`**. Primary demo manager: **`ada@acme.test`**.

## What it creates (verified counts after a run)

- **236 people** across a multi-level org (admin → 2 HRBPs → 6 directors → 18 team leads → ~205
  employees), realistic varied names, real roles + manager links. (Org tree = `User.manager`.)
- **H1 2026 cycle** with goals + KPIs for **every non-admin** — **two goals weighted 60 + 40 = 100**
  (KPIs within each goal also sum to 100), recorded actuals on a deterministic spread → **233 cycle
  scores** that vary believably (**181 ON_TRACK / 52 AT_RISK**). **Stray goals from old sessions are
  archived**, so **no person shows 200/100** (verified: 0 employees with active-goal weight ≠ 100).
- **72 reviews** across all states (DRAFT / PENDING_HUMAN_REVIEW / APPROVED / FINALIZED / REJECTED /
  EDITING) so the Reviews list is full. A **guaranteed DRAFT review for `emp009@acme.test`** (an Ada
  report, with a self-assessment, reset on every run) keeps the "Request AI draft" demo reliable.
- **10 × 360 feedback cycles** — **6 CLOSED + summarizable** (≥3 PEER responses; a PENDING summary
  artifact exists, AI theme text intentionally left ungenerated), **3 COLLECTING** (in progress, incl.
  a PENDING request to Ada), 1 draft.
- **366 weekly check-ins** across the last 4 weeks (many employees) + a manager response.
- **28 recognitions** across all visibility levels.
- Pending work for **Ada**: **3 pending approvals** (real approval routes/steps assigned to her),
  **2 feedback asks**, **10 reports with reviews**, **17 reports** (13 on-track / 4 at-risk scored).
- **Succession**: 3 critical roles + bench + a 9-box grid + a PENDING plan. **JD library**: 6 JDs
  (4 published). FULL_AI entitlement (250 seats).

## Intentionally EMPTY (no real data source — honest, do not fabricate)

- **Engagement score**, **team-competency radar**, **announcements**, the **notifications feed**.
  These have no backing model, so they stay as honest empty states (per N6). If asked in the demo:
  *"That needs a real data source we haven't built yet, so we show an honest empty state rather than
  invent a number."*

## Ada's dashboard will be full

Logged in as `ada@acme.test`, the manager cockpit has real data in: **Reviews to action**, **At-risk
reports** (KPI Intelligence nudges — FULL_AI), **Pending approvals** (3), the team performance table
(17 reports with T-scores), and **feedback asks** (2). The recompose's "Needs you" / Quick-access
surfaces are populated too.

## Verification done

- Ran the command twice → stable at 209 generated people, **0** weight violations on the second run
  (idempotent).
- **Full backend suite: 1327 passed.** Frontend build: green.
- web + celery-worker recreated; `http://localhost:8080` returns 200.

See **DEMO_WALKTHROUGH.md** for the live, step-by-step CEO/Tech-Head demo script using these records.
