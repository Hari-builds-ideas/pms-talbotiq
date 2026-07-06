# PMS — State of the Project (honest, for the final push)

**Date:** 2026-06-29 · **Branch:** main @ `3037ec7` · **Backend tests:** 1300 passing, 2 deselected
(heavy `large_tenant`) · **Frontend:** build green, tsc/lint clean, vitest 105 passing (20 files) + axe a11y guard.

> Read this as: what's *real and proven*, what's *real but unproven live*, and what's *intentionally
> stubbed*. "Verified" below means **I or you clicked it live this session**; "test-only" means a passing
> automated test exists but nobody has clicked it end-to-end on the running app.

---

## 1. Feature status (honest)

| Feature | Status | One-line truth |
|---|---|---|
| Auth + JWT login | **FULLY WORKING** | Live-verified (password login, tenant slug, MFA seam). |
| RBAC + tenant scoping | **FULLY WORKING** | Enforced server-side everywhere; heavy test coverage; chat inherits it (proven). |
| SSO (SAML + OAuth) | **PARTIAL** | Proven against a **mock/test IdP** only (W1 + tests). No real Okta/Azure/Google app configured. |
| Goals & KPIs | **FULLY WORKING** | CRUD + approve + KPI actuals; approve-state bug (BUG 1) fixed + verified. AI goal-writer wired (HITL draft). |
| Reviews + HITL (manual) | **FULLY WORKING** | Draft→edit→submit→approve→finalize state machine; review comments; advisory AI quality flag live-verified. |
| Reviews — **AI draft (Agent 1)** | **PARTIAL** | Real agent, gateway→OpenAI, locked PENDING. **Async (Celery+poll); NOT live-verified** (task #59 open). |
| 360 Feedback + anonymization | **PARTIAL** | Cycle/invite/give/close + anonymization are test-solid. **AI summary (Agent 3) is real but async + unproven live.** |
| Approvals (sequential/parallel matrix) | **PARTIAL** | Workflow + route + step approve/reject test-solid; not clicked through a full multi-step route live. |
| Recognition (kudos) | **FULLY WORKING** | Feed + give + react, visibility enforced server-side; UI wired (RW_BUILD_2). |
| Check-ins (weekly) | **FULLY WORKING** | Employee loop + manager response; AI meeting-summary live-verified (RW_BUILD_3 + AI #1). |
| Org chart | **PARTIAL** | Lazy-load tree + person cards test-solid (BUILD_6); not stress-clicked live on a big tenant. |
| Succession (nine-box, bench) | **PARTIAL** | Nine-box reposition + bench/readiness test-solid (BUILD_7). **AI enrich (Agent 4) real but async + unproven live.** |
| JD generator + library | **PARTIAL** | JD lifecycle (draft/submit/approve/archive) test-solid; partial-body crash fixed. **AI generate real but async + unproven live.** |
| Career roadmap | **PARTIAL** | Deterministic target→roadmap + employee read-only view (BUG 3 fixed). **AI enrich real but async + unproven live.** |
| Analytics (individual/dept/calibration) | **PARTIAL** | Deterministic rollups work. **The AI insights narrative is STUBBED** (`ANALYTICS_INSIGHTS_PROVIDER` = NotConfigured). |
| AI #1 — meeting summary | **FULLY WORKING** | Live-verified; prompt+schema hardened (D37 + Finding D). |
| AI #2 — review quality flag | **FULLY WORKING** | Live-verified; advisory, non-blocking, quotes the phrase. |
| AI #3 — stale-goal nudge | **FULLY WORKING** | Live-verified; manager/HR dashboard tile, read-only + advisory. |
| AI #4 — NL search (via chat) | **FULLY WORKING** | Live-verified; scope-bound, manager/HR only; costs 2 LLM calls/query. |
| AI #5 — approve_reviews (via chat) | **FULLY WORKING** | Proposal live-verified (inert); execute = the human path, audited. |
| Chat assistant (read-only) | **FULLY WORKING** | Live-verified; RBAC-bound, intent-classified, write→propose-or-refuse. |
| Admin / tenant config / entitlements / billing | **PARTIAL** | Users (paginate/search), tenant config, packs/seats test-solid; not clicked through every admin path live. |
| Jira / Slack integrations | **STUBBED (by design)** | NotConfigured/log-and-skip; no real client wired (Module 12 deferred). |
| Mobile surface | **NOT BUILT** | BUILD_8/9 pending; shared layer extracted, but no mobile app. Employee dashboard says so explicitly. |

**Bottom line on AI:** two parallel systems. (a) The **chat + 5 quick wins** are synchronous, gateway-routed,
and live-verified — solid. (b) The **original async agents** (review draft / 360 summary / succession /
JD / career enrich) are *real code* through the same gateway but run on Celery and have **never been
clicked end-to-end** — treat them as unproven. **Analytics-insights AI and Jira/Slack are genuinely off.**

---

## 2. What each role actually sees (end-to-end)

Nav was re-cut per role (RW_BUILD_1), so **no known dead links / "no access" on advertised items**. BUG 3
(employee career dead link) is fixed. Per-role cockpits are real, composed from live endpoints:

- **Employee** — My goals, My review, My feedback requests, My roadmap (read-only own), stat cards. Holds
  up. (No team tabs, no manage controls — correct.)
- **Manager** — Pending approvals, At-risk reports (Agent-2 KPI nudges, gated to FULL_AI), Reviews to action,
  Reviews-awaiting tile, **Stale-goals tile (new)**, approvals inbox, check-ins "My team" + AI summary,
  chat (NL search + approve proposals). Holds up.
- **HRBP** — Summaries to release, coverage gaps, approvals, at-risk, succession-risk tile, nudges,
  stale-goals tile. Holds up.
- **Admin** — Active users, plan/seats, critical roles, recent audit, tenant health, entitlements. Holds up.

**Confusing-but-not-broken:** on a **STARTER** tenant, AI tiles ("At-risk reports", locked features) render
as **"locked / upgrade"** by design — fine in product, awkward in a demo. Demo on **acme** (FULL_AI).

---

## 3. Known bugs / rough edges right now

1. **Stale gunicorn workers (DEV only).** Gunicorn doesn't auto-reload; after a backend code change the
   lazily-imported AI views throw `ImportError` → intermittent **HTTP 500** until `web` is recreated. Caused
   the meeting-summary "fails 3-of-4" symptom. Prod deploys restart workers, so this is a dev-workflow trap,
   not a product bug. Fix: recreate `web` after edits (or add gunicorn `--reload` in dev compose).
2. **Async AI agents unproven live** (see §1) — the biggest unknown; could degrade or error on first real click.
3. **Analytics AI narrative is off** — analytics shows numbers, no AI insight (NotConfigured). Not a crash.
4. **NL-search-via-chat = 2 LLM calls/query** (chat classify + search classify) — extra latency/cost.
5. **Uncommitted working tree:** `docs/AI_GOLIVE.md` (stray edit), `HANDOVER.md`, `docs/INNOVATION_PITCH.md`,
   `docs/NEW/` — cosmetic, but tidy before sharing the repo.
6. **A very slow OpenAI call can 504** (30s×3 attempts vs 60s gunicorn / 65s nginx). Rare.

No known endpoint that 500s in normal use **once `web` is current**. No half-built screens found
(0 TODO/stub markers in frontend; backend `NotImplementedError`s are abstract bases + intentional NotConfigured fallbacks).

---

## 4. Demo-readiness (if demoing in ~20 hours)

**SAFE to show live (reliable):**
- Login + role switch (employee/manager/HRBP/admin) on **acme**.
- Goals: create, approve, record KPI actuals. Reviews: edit → submit → approve → finalize (manual path).
- Recognition feed; weekly check-ins (employee submit + manager respond).
- **The 5 AI quick wins** — meeting summary, review-quality flag, stale-goal nudge tile, NL search in chat,
  approve-reviews proposal in chat. All live-verified this session.
- Read-only chat assistant (RBAC-bound answers; write refusal).
- Dashboards, org chart, succession nine-box, JD library (manual), analytics numbers.

**RISKY (intermittent / unfinished — rehearse or avoid):**
- **"Request AI draft" on a review, AI 360 summary, AI JD generate, AI career/succession enrich** — async +
  never clicked live; depends on the Celery worker + OpenAI. **Rehearse once before showing, or skip.**
- Any AI feature **if the OpenAI account is out of credit / rate-limited** (see §6).
- Anything **right after a code edit** without recreating `web` (stale-worker 500).
- STARTER-tenant AI surfaces (show "locked").

---

## 5. Local-vs-production gap

**Runs today fully on free/local tiers** via `docker compose up`: web (gunicorn), frontend (nginx),
MySQL, Redis, Celery worker + beat, Flower — all local containers on `http://localhost:8080`. **The only
paid dependency is the OpenAI key** (cents for a demo; or swap to Groq free tier by config —
`LLM_PROVIDER=apps.ai.groq.GroqProvider`). **A demo needs nothing but Docker + the key.**

**Would need to swap for real production:**
- **Hosting + TLS** — currently HTTP on localhost; needs a host + certs (no HTTPS today).
- **Managed DB/Redis** — single MySQL + single Redis container, no backups/replication/failover.
- **Secrets** — `SECRET_KEY` + `OPENAI_API_KEY` live in `.env`, not a vault/secrets manager.
- **SSO** — proven vs a mock IdP only; real Okta/Azure/Google needs a registered app + config.
- **Email** — transactional email not wired for production delivery.
- **Scale/security review** — multi-tenant isolation is enforced in code + tested, but no load test or
  external pen-test has been run.

**Is local solid for a demo?** Yes, with two caveats: (1) confirm OpenAI credit/limits (§6), and
(2) recreate `web` after any change. Graceful degradation is real — with no/blocked AI, features return a
clean 503/"unavailable" or fall back to the deterministic path; they don't crash.

---

## 6. AI cost / limits (real numbers)

- **Model:** `gpt-4o-mini` (cheap — roughly $0.15 / $0.60 per 1M input/output tokens). A whole demo
  (dozens of calls, ~hundreds–1k tokens each) costs **cents**.
- **App global ceiling:** `LLM_MAX_CALLS = 500` per **24h**, cache-counted and process-shared. Exceed it →
  AI returns **429 "budget exhausted"** (graceful). Counter was at ~11/500 today — fine, but **heavy
  pre-demo testing could approach it**; it resets after 24h (or clear the `llm:global:calls` cache key).
- **Per-tenant per-agent budget:** FULL_AI = **500/day, 10000/month**; STARTER = 50/day, 1000/month. acme is FULL_AI.
- **Per-user AI rate limit:** FULL_AI = **120/min**; STARTER = 20/min. Won't trip in a manual demo.
- **OpenAI account quota (NOT visible from the app — YOUR account):** if the key's account is out of
  credit or hits its TPM/RPM limit, OpenAI returns 429 → the provider retries 3× then degrades to a clean
  503/PROVIDER_ERROR (no crash, no fabricated output). **Confirm the account has credit + sane rate limits
  before the demo** — this is the single most likely thing to make AI "fail" live.

---

## Honest assessment

**Is this a real product today?** Yes — genuinely. It's a multi-tenant, RBAC-enforced PMS with ~1300
passing backend tests, a real typed React frontend (a11y-guarded), an audit-logged write path, an
entitlements/billing model, and AI that runs through a safety gateway with human-in-the-loop and graceful
degradation. The architecture (tenant scoping, HITL, no fabricated AI) is sound, not a façade. It is,
however, **dev-stage**: single-node Docker, no hosting/TLS/vault, SSO only vs a mock IdP, the async AI
agents unproven live, a couple of AI seams intentionally off, and no mobile app.

**Top 5 to fix before a demo:**
1. **Live-verify the async AI agents** (review draft, 360 summary, JD generate, career/succession enrich)
   with the Celery worker running — task #59. Either confirm they work and add them to the script, or keep
   them off it. This is the biggest gap between "looks done" and "is done."
2. **Confirm the OpenAI account has credit + adequate rate limits.** The likeliest live-demo failure.
3. **Recreate `web` after any code change** (or add gunicorn `--reload` in dev) — kill the stale-worker 500.
4. **Lock the demo to `acme` (FULL_AI)** with its rich seed; avoid STARTER tenants (locked AI tiles).
5. **Tidy the tree** (commit/discard the stray docs) and **reset the global AI counter** if you've tested heavily.

**What "finishing" means from here:**
- **To demo well (hours):** items 1–5 above. The core flows + the 5 AI quick wins already demo cleanly.
- **To ship to a real customer (weeks):** real hosting + TLS + managed DB/Redis + a secrets vault; SSO
  against a real IdP; harden + observe the async AI agents (retries, timeouts, dead-letter); decide
  whether to finish analytics-insights AI and Jira/Slack; build the mobile surface (BUILD_8/9); and a
  load + multi-tenant security review before onboarding real tenants.
