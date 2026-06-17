# PRODUCT_STATE.md — Talbotiq PMS, as-built state of the product

> One honest source of truth for planning the next phase. Grounded in the **actual
> code + repo state** at commit `1e43a7a` (not the old reports). Where a past report
> and the code disagree, the code wins and the drift is flagged **⚠**. Verification
> honesty is marked throughout: **[live]** exercised over real HTTP against the
> running stack; **[build]** confirmed by build/tsc/lint/tests; **[code]** read in
> source but not separately exercised; **[unproven]** wired but not verified at scale.
> No code was changed to produce this report. AI status is read from config/code — no
> Groq calls were made.

---

## 1. Executive snapshot

Talbotiq PMS is a **multi-tenant, RBAC, AI-assisted performance-management system**
(Django 4.2 + DRF + MySQL + Redis/Celery backend; React 18 + TS + Tailwind/shadcn
frontend; Groq LLMs through one safety gateway). It runs as **one Docker stack** with
the React Admin Hub on the real API, seeded demo data (acme = FULL_AI, globex =
STARTER), and the AI agents live on Groq.

**What genuinely works end-to-end today [live]:** the full performance lifecycle —
goals/KPIs → reviews (with AI draft + HITL) → 360 feedback (request→give→AI summary→
HRBP release→subject view) → approvals routing → org chart → succession (generate→
enrich→publish) → career roadmaps → analytics (with min-cohort suppression) → admin/
billing/entitlements/integrations/audit → AI chat. A repeatable smoke script passes
**47/47** core journeys with every RBAC/scope/tenant boundary holding.

**Honest completion picture:** **Backend** — feature-complete for the 14-module MVP
build order, **1059 tests passing**. **Web frontend** — every screen built, wired to
real data, and re-skinned to the new indigo design system; but several screens are
**UX-shallow** (data dumps, not insight) per the redesign audit. **AI** — live on Groq
and quality-tuned, but proven on only **1–2 records per agent** (free-tier discipline),
not at scale. **Mobile** — **plan only, not built**. **Go-live** — not done (secrets
vault, hosting, provider tier, full QA sweep remain).

**The single most important next thing:** decide the **AI provider tier + secrets
store** and run a **real-data AI-quality pass at small scale across all agents** — the
AI is the product's differentiator and is currently proven only on a 1–2 record sample.

---

## 2. Architecture as-built

**Backend (real):** Python 3.11 · Django 4.2 · DRF · MySQL 8 · Redis 7 · Celery
(worker + beat) · Argon2 passwords · JWT (simplejwt) + django-allauth (OIDC) +
django-otp (MFA). ~20 apps under `apps/` (identity, tenancy, rbac, goals, cycles,
reviews, feedback, approvals, jd, org, succession, career, analytics, billing,
administration, integrations, audit, ai, core, testsupport).

**Frontend (real, post-re-skin):** React 18.3 · TypeScript · **Tailwind v3.4** (the
Figma export is v4; we re-skinned **in place** on v3 — see §5) · shadcn/Radix
components · React Query · RHF + zod · React Router · **cmdk** command palette ·
**recharts** · sonner toasts. Design tokens: **indigo `#5B5BD6`** primary, near-black
`#0C0C14` sidebar, **Plus Jakarta Sans + DM Mono**. Served by an nginx edge that
proxies `/api,/admin,/accounts,/static,/healthz,/readyz` → the Django web tier.

**AI / Groq:** all LLM calls flow through **one `LLMGateway`** (`apps/ai/gateway.py`).
- ⚠ **Code default vs running stack:** `settings.LLM_PROVIDER` defaults to
  `NotConfiguredProvider` and `LLM_MAX_CALLS=0` — i.e. **a fresh clone with no key
  serves a graceful 503 on every AI surface**. The **running Docker stack overrides
  via `.env`** to `apps.ai.groq.GroqProvider`, key present, `LLM_MAX_CALLS=60`
  [live-confirmed from config]. So "AI is live" is true *of the running stack*, not of
  the default config.
- Two-model map: `llama-3.3-70b-versatile` (review/feedback/succession/jd/career),
  `llama-3.1-8b-instant` (chat/default). LangSmith opt-in (no-op until keyed).
  `langgraph` is installed; the agents currently run via an in-repo `run_graph`
  stand-in (a faithful `StateGraph` substitute — a real-LangGraph swap is optional).

**Infra:** `docker compose up -d --build` brings up mysql, redis, web (gunicorn,
auto-migrate on start), celery-worker, celery-beat, flower, frontend (nginx).
`seed_demo` is idempotent (runs twice clean).

**Cross-cutting invariants (as implemented in code):**
- **Tenancy:** every model is `TenantScopedModel` (UUID pk + tenant FK); a
  `TenantScopedManager` filters by tenant; the JWT carries `tenant_id` (client never
  sends it); cross-tenant rows → **404, never 403**.
- **RBAC:** capabilities in `apps/rbac/matrix.py` (4 roles) + data scope in `scope.py`
  (OWN/TEAM/TENANT), checked server-side on every endpoint; the frontend gates UI for
  UX only.
- **Audit:** `AuditLog` is INSERT-only; the console is read-only (no mutation route).
- **HITL:** every AI/automated artifact is locked PENDING until a human acts
  (review approve→finalize, feedback summary release, succession publish, JD approve→
  publish, career advisory).

**Request flow (as-built):**
```
Browser (React, JWT in memory)
  │  Authorization: Bearer <access>      (refresh via axios interceptor on 401)
  ▼
nginx edge ──proxy──► Django/DRF view
  │                     ├─ IsAuthenticated + HasCapability (RBAC matrix)
  │                     ├─ WithinScope / actor_can_access (data scope → 404)
  │                     ├─ service layer (the sole mutator; audits BEFORE effect)
  │                     └─ TenantScopedManager ──► MySQL
  │
  └─ AI surface (e.g. request-ai-draft, close 360, enrich) ──►
        LLMGateway: budget reserve → PII-scrub(emails) → Groq (LangSmith span)
                    → schema-validate → meter to TokenLedger → confidence/floor
                    → result locked PENDING_HUMAN_REVIEW  (never auto-final)
        (no provider/key → NOT_CONFIGURED → HTTP 503; deterministic path still works)
```
Real-time: **no websockets/SSE** — the frontend polls/refetches after actions.

---

## 3. Feature inventory

Backend status: **Real+Tested** unless noted. Frontend: **Built** (wired to real
data) → all screens are **re-skinned** (indigo system applied app-wide); "weak" =
UX-shallow per the redesign audit. AI: **Live(Groq)** / **Deterministic** / **503 by
default** (live in the running stack). Verdict = honest real-vs-shallow.

| Module | What it does | Backend | Frontend | AI | Verdict |
|---|---|---|---|---|---|
| **Auth / MFA / OIDC** | tenant-qualified login, TOTP MFA, allauth OIDC handoff, JWT + refresh | Real+Tested | Built+re-skinned | — | **Real.** Login [live]. MFA enrol/challenge wired [code]; no MFA-enrolled demo account [unproven end-to-end in demo]. OIDC handoff [code], not exercised live. |
| **Goals & KPIs** | weighted goals, KPIs, append-only actuals, deterministic T/Z scoring, recompute, approve | Real+Tested | Built, **weak** (form-dump dialog, 1-by-1 actuals, no progress viz) | — | **Real engine** [live: list/score/recompute/actual]. UX shallow. |
| **Reviews + HITL** | DRAFT→AI_DRAFTING→PENDING→APPROVED→FINALIZED; AI draft; approval-route hook | Real+Tested | Built (arch strong, AI UX async/janky) | **Live(Groq)** Agent 1 | **Real.** AI draft [live, 1 record], names person + cites goals/KPIs/numbers. |
| **360 Feedback** | cycles, invitations, anonymised egress, Agent-3 summary, HRBP release, my-cycles | Real+Tested | Built+re-skinned | **Live(Groq)** Agent 3 | **Real, the strongest AI loop** [live, 2 cycles incl. a suppressed group]. |
| **Approvals** | SEQUENTIAL/PARALLEL workflows, inbox, route tracker, escalation | Real+Tested | Built (designer weak — list, no visual editor; no notifications) | — | **Real** [live: inbox/workflows]; an end-to-end route not re-verified live this session [unproven]. |
| **JD Library** | author/generate/approve/publish/version/requests | Real+Tested | Built (textarea editor; AI one-shot; no version diff) | **Live(Groq)** JD generator | **Real.** AI generate [live, 1 JD]. |
| **Org chart** | scoped tree + rollups, positions (fill/close/link-JD), reassign (cycle-checked) | Real+Tested | Built (no connectors/search, no analytics) | — | **Real** [live: tree/positions/reassign-scope]. UX shallow. |
| **Succession** | critical roles, bench/readiness, 9-box, plan generate→publish, Agent-4 enrich; **employee→404** | Real+Tested | Built, **weak** (no bench-depth preview, non-interactive 9-box, no plan detail) | **Live(Groq)** Agent 4 | **Real + privacy-correct** [live: dashboard/9-box/enrich, employee 404]. |
| **Career roadmap** | target → deterministic roadmap (skill gap + tiers) + per-tier progress + AI enrich | Real+Tested | Built this run, **weak** (abstract tiers; no progress-to-target) | **Live(Groq)** career agent | **Real** [live: roadmap/skill-gap/progress/regenerate]. ⚠ AI enrich has **no accept→ACTIVE** endpoint (stays DRAFT). |
| **Analytics** | individual trend, department (min-cohort <5 suppression), calibration grid | Real+Tested | Built, **weak**; trend now a **recharts** chart | Deterministic (no AI) | **Real** [live: individual/calibration; employee→department 403]. The 4-vs-5 suppression boundary not re-verified live this session [code]. |
| **Billing / entitlements** | seats, packs (STARTER/FULL_AI), feature-flag map, upgrade (flips flags), my-features | Real+Tested | Built (no usage/cost story) | — | **Real** [live: reads]; an actual upgrade-flip not exercised this session (would mutate globex) [code]. |
| **Admin (users/roles/tenant-config)** | create/role/reporting-line/display-name/(de)activate; tenant settings | Real+Tested | Built; tenant-config is **raw JSON** (weak) | — | **Real** [live: users read; create [code]]. |
| **Audit console** | immutable, filterable action history; read-only | Real+Tested | Built (no date range, raw action strings) | — | **Real** [live: read + RBAC]. |
| **Integrations (Jira/Slack)** | per-tenant config + `secret_ref` (env-var NAME, never a token) | Real+Tested (fakes) | Built, **weak** (no test-connection, no event log) | — | **Real-but-no-op:** no real Jira/Slack creds anywhere; stays a clean no-op until a secret is provided [code]. |
| **AI Chat** | read-only, RBAC-bound NL assistant; write intent blocked | Real+Tested | Built (no streaming/history) | **Live(Groq)** 8B | **Real** [live: grounded answer / out-of-scope empty / write blocked]. |
| **AI agents (the suite)** | see below | — | — | — | — |

**AI agent taxonomy (as implemented):** Agent 1 Review (LLM, FULL_AI) · Agent 2 KPI
Intelligence (**deterministic nudges, no LLM** + drives chat intent, STARTER) · Agent
3 Feedback summary (LLM, FULL_AI) · Agent 4 Succession (LLM, FULL_AI) · JD generator
(LLM, FULL_AI) · Career roadmap (LLM, FULL_AI) · Chat (LLM 8B, STARTER).
⚠ **`agent5` is a reserved FULL_AI feature flag with NO implementation** (there is no
agent5 in `apps/ai/agents/`) — the "5 agents" framing in older docs overcounts; there
are **4 numbered agents + JD + career + chat** implemented, one deterministic.

---

## 4. What is genuinely done vs shallow/missing (brutally honest)

**Genuinely done + verified:**
- The whole **backend** for the 14-module MVP — real services, real scoping, **1059
  tests**, idempotent seed. This is the strong foundation.
- The **360 feedback loop** end-to-end incl. real anonymisation + a real Agent-3
  summary + HRBP release [live].
- **RBAC/scope/tenant isolation + HITL gates** — verified by the smoke (47/47) and the
  test suite; succession is correctly invisible to employees (404).
- **AI output quality** was genuinely improved (rich evidence + grounded prompts +
  tightened schemas) and **proven on 1–2 records per agent** [live].
- The **re-skin** is real and app-wide (indigo/dark/new fonts) with **zero wiring
  loss** (smoke still 47/47 after it).

**Shallow / weak (works, but not premium — from the redesign audit, `docs/frontend-
redesign/`):** the **role dashboards** (tile dumps, no insight/bulk actions),
**Goals** (form-dump create, 1-by-1 actuals), **Career** (abstract tiers), **Succession**
(non-interactive 9-box, no plan detail), **Analytics** (thin viz), **Tenant Config**
(raw JSON), **Integrations** (no test/log), **Chat** (no streaming/history). All real,
all re-skinned — but UX-shallow.

**Wired but unproven (this session):** an end-to-end **approval route**; the
**entitlement upgrade flip** (avoided — it mutates globex); the **analytics 4-vs-5
suppression boundary** (logic tested in the suite, not re-clicked live); **MFA** and
**OIDC** flows (no enrolled demo account / no IdP wired); **AI at scale** (only 1–2
records per agent).

**Mock-only / not built:**
- **Mobile app** — plan only (`MOBILE_BUILD_PLAN.md`); nothing built.
- **Employee experience in the *web* Admin Hub** — the hub is Manager+ (every route
  `min="MANAGER"`); an employee gets only a cockpit, no nav. Employee self-service is
  intended for mobile (not built). ⚠ Older contract docs implied an employee web
  surface; the real router does not provide one.
- **`agent5`** — reserved flag, no agent.
- **Real Jira/Slack** — no credentials; no-op adapters only.
- The frontend has an **MSW mock layer** for dev, but the shipped build runs against
  the **real API** (`VITE_USE_MOCKS=false`); no screen is mock-only in the deployed app.

---

## 5. Known issues, risks & tech debt

**Open NEEDS_HARI decisions (repo root):**
- `NEEDS_HARI_llm_provider.md` — provider/tier choice (superseded operationally by
  `docs/AI_GOLIVE.md`, but the **production tier** call is open).
- `NEEDS_HARI_analytics_scope.md` — is Analytics in the July-7 MVP or Phase 2? (built;
  revertible as a unit). Min-cohort = 5, "department = manager subtree" — confirm.
- `NEEDS_HARI_secrets.md` — production secrets store for integrations (env-var
  `secret_ref` today; needs a vault for multi-tenant prod).
- **Resolved:** `NEEDS_HARI_pack_mapping.md` (**Agent 1 → FULL_AI**, applied) and
  `NEEDS_HARI_feedback_subject_discovery.md` (**my-cycles** built + wired).
- **No BLOCKER_*.md files exist.**

**Drift the code corrects vs older reports:**
- ⚠ `/api/auth/me` now returns `tenant_name` + `tenant_slug` (older screen docs listed
  only `{id,email,role,tenant,mfa_enabled}`).
- ⚠ `my-features` is readable by **all roles** (older overview hedged it was admin-only).
- ⚠ **Duplicate calibration:** `/api/reviews/calibration` exists but is **unused** — the
  UI uses `/api/analytics/calibration`. Cleanup candidate.
- ⚠ **Career AI roadmap** has **no accept→ACTIVE endpoint**; an enriched AI roadmap
  stays a DRAFT alongside the deterministic one (the "human acceptance" is conceptual).
- ⚠ **`agent5`** reserved flag, unimplemented (older "5 agents" framing overcounts).
- ⚠ **Re-skin state:** the Figma export is **Tailwind v4**; we re-skinned **in place on
  v3** by porting the look (not adopting the export's component files). Adopting them
  verbatim would require a v4 migration (a separate track). The rendered appearance is
  **not pixel-verified** (agent can't see pixels) — `RESKIN_MORNING_REPORT.md` lists
  the visual calls for Hari.

**Risks / tech debt:**
- **Groq free tier:** global ceiling 60/run + per-tenant budgets + 429 back-off. Fine
  for demo; **a real customer needs a paid tier** + raised budgets.
- **Secrets in `.env`** (gitignored, never committed) — fine for demo; **needs a vault**
  for prod (integrations + the Groq key).
- **AI proven only at 1–2 records** — quality at scale + edge cases (thin evidence,
  breach holds, 429s) is **unproven**.
- **No CI** observed in-repo; tests are run manually. No load/security testing.
- **Single VM / docker-compose** topology; no production hosting/scaling defined.

---

## 6. Quality & test status

- **Backend:** **1059 tests passing** [live, this report] (`pytest -q`, ~88s); 82 test
  files; covers models/services/RBAC/scope/tenant isolation/state machines/the AI seams
  under a deterministic FakeLLMProvider. Strong.
- **Frontend:** `tsc --noEmit` ✓, `eslint .` ✓, `npm run build` ✓ [build]. **25 Vitest
  tests** (4 files) over the **load-bearing logic only**: the error-code mapper,
  RBAC/feature-flag gating (RoleGate/FeatureGate), HITL/confidence rendering, the KPI
  weight rule. **Not covered:** screen/integration tests, the data hooks, the command
  palette, the charts, routing. Meaningful-but-thin.
- **Smoke:** `scripts/smoke.py` = **47/47** [live] — every surface's core journey + the
  RBAC boundaries (admin/audit denied to manager, succession 404 for employee, dept
  analytics + nudges denied to employee, chat write blocked). It is read-mostly and
  repeatable.
- **Not tested anywhere:** real Groq output quality (deliberate — fakes in tests),
  visual appearance, real Jira/Slack, MFA/OIDC live, load/security.

---

## 7. What remains to be production-ready (with size S/M/L)

**(a) Finish-the-web (UX depth, from `docs/frontend-redesign/ux-spec.md` §8.3):**
- Command-center dashboards (insight + bulk actions, not tile dumps) — *biggest lift* — **L**
- Goal-creation wizard + live weight bar + attainment gauges — **M**
- Review AI streaming/optimistic + draft-vs-final diff + comments — **M**
- Career progress-to-target + concrete tiers; resolve the AI accept→ACTIVE gap — **M**
- Succession coverage heatmap + interactive 9-box + plan detail — **M**
- Breadcrumbs (primitive in place), more recharts, typed tenant-config form — **S–M each**

**(b) AI quality / go-live (`docs/AI_GOLIVE.md`):**
- Small-scale **real-data quality pass across all agents** (tune prompts/evidence/schema) — **M**
- Pick provider **tier** + move the key to a vault; confirm per-tenant budgets; raise the ceiling — **S–M**
- (Optional) swap the in-repo graph runner for real LangGraph; enable LangSmith tracing — **M**

**(c) Mobile (`MOBILE_BUILD_PLAN.md`, plan only):**
- Expo/RN app, employee/manager self-service; extract a shared API/types/auth layer;
  the `my-cycles` endpoint it needs already exists — **L (multi-session)**

**(d) Hardening / QA / handoff (Module 14 — the July-7 QA target):**
- Full QA sweep + the QA PDF + handoff docs; frontend screen/integration tests; CI — **M–L**
- A real end-to-end exercise of the unproven flows (approval route, upgrade flip,
  MFA/OIDC, suppression boundary) — **S–M**

**(e) Pre-real-customer:**
- Secrets vault (Groq key + integration tokens) — **M**
- Production hosting/scaling (beyond single-VM compose), backups, monitoring — **L**
- Paid Groq (or alternate provider) tier — **S** (decision) **/ M** (wiring)

---

## 8. Recommended roadmap (next 3–5, sequenced, with reasoning)

1. **AI go-live decisions + a real-data quality pass (b).** *Why first:* the AI is the
   differentiator and is proven on only 1–2 records; the provider-tier + secrets calls
   gate everything else AI. Small effort, high signal. **Needs your decision** (tier,
   secrets store). 
2. **Verify the unproven flows end-to-end (d, the S–M slice).** *Why:* cheap insurance —
   prove the approval route, the entitlement upgrade flip, MFA/OIDC, and the analytics
   suppression boundary live before building more on top. Closes "wired-but-unproven".
3. **Finish-the-web Tier-1 UX (a).** *Why:* the screens are real but shallow; the
   command-center dashboards + goal wizard + review AI streaming are the lifts that make
   it *feel* like a product. Do these before mobile so the patterns are settled. **Your
   visual judgement** (from `RESKIN_MORNING_REPORT.md`) feeds this.
4. **Module-14 QA hardening + handoff (d).** *Why:* the July-7 QA handoff target — full
   sweep, screen tests, CI, the QA PDF. Sequence after the UX so QA tests the finished
   surfaces.
5. **Mobile build (c)** *or* **pre-customer hardening (e)** — *whichever the business
   needs first.* **Needs your decision** (mobile go/no-go vs. go-live hardening).

---

## 9. Open decisions for Hari (with current default + implication)

| Decision | Current default | Choosing each way implies |
|---|---|---|
| **AI provider tier** | Groq free tier (ceiling 60/run, small budgets) | Free = demo only (rate limits at any real load). Paid Groq / alt provider = production AI; gateway is provider-agnostic, so it's config + a key (`docs/AI_GOLIVE.md`). |
| **Secrets store** | env-var `secret_ref` + Groq key in gitignored `.env` | Fine for demo. For multi-tenant prod: a vault (AWS/GCP Secrets Manager / Vault) — `resolve_secret` is one function to swap. |
| **Agent-1 pack** | **RESOLVED — FULL_AI (premium)** | Done; STARTER = {agent2, chat}. No action unless you want to revisit. |
| **Analytics in MVP** | Built + in scope | Keep = no action. Defer to Phase 2 = the `apps/analytics` app + routes + 3 RBAC keys revert as one additive unit. Confirm min-cohort=5 + "department = manager subtree". |
| **Mobile go/no-go** | Plan only, not built | Go = a multi-session Expo/RN build (`MOBILE_BUILD_PLAN.md`); needs Apple/Google accounts at release only. No-go = employee self-service stays unavailable (the web hub is Manager+). |
| **Dark mode** | Light only (re-skin deferred dark) | Add later = wire the export's oklch dark tokens + a toggle + verify every screen in both themes. |
| **Re-skin depth** | In-place v3, port-the-look (light) | Keep = current premium look, lowest risk. Adopt Figma component files verbatim = a Tailwind v4 migration (separate, larger track — `docs/RESKIN_PLAN.md` §3). |
| **`agent5` flag** | Reserved, unimplemented | Implement a 5th agent, or remove the flag to avoid confusion. |
| **`/reviews/calibration` dup** | Present but unused | Remove (the UI uses `/analytics/calibration`) — small cleanup. |
| **Career AI accept** | AI roadmap stays DRAFT (no activate endpoint) | Add an accept→ACTIVE endpoint, or formally present the AI roadmap as an advisory alternative. |

---

*Generated from the repo at `1e43a7a`. Backend 1059 tests passing; frontend build/
typecheck/lint green; smoke 47/47; AI live on Groq in the running stack (503 by
default config). Accuracy over optimism — see the ⚠ drift flags throughout.*
