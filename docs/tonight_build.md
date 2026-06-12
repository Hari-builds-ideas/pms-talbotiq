# TONIGHT_BUILD.md — Autonomous Overnight Build Plan (Talbotiq PMS)

> Hari is asleep. You are running unattended in AUTO MODE on **Claude Opus (do NOT switch models)**.
> Your job: build as many of the modules below as you can, IN ORDER, to production quality,
> committing locally after each one passes. Read this entire file first, then read `CLAUDE.md`
> and `docs/BUILD_NOTES.md`, then begin at Module 9.

---

## 0. OPERATING CONTRACT — read carefully, these rules override convenience

1. **Order is fixed.** Build in this order and do not skip ahead:
   **M9 Career → M11 Billing/Entitlements → M-Analytics → M12 Integrations → M10 AI Agents.**
   (This is value × safety ordered: deterministic modules first, the AI agents last.)

2. **Hard gate between modules.** You may ONLY start a module if the previous module:
   (a) has its FULL test suite green on MySQL in Docker, AND
   (b) is committed locally. If either is false, STOP (see rule 5).

3. **Production quality only.** Real MySQL-backed tests (run in Docker, the project's only supported
   path). No placeholders, no TODOs, no stubbed logic, no fake test data masquerading as real behaviour.
   Every model inherits `apps.tenancy.models.TenantScopedModel`. Every endpoint is RBAC-gated
   (`RBACMixin` + a Capability + `WithinScope`) with new capability keys added to `apps/rbac/matrix.py`
   and the matrix oracle test extended. Every consequential action writes an `apps.audit.services.record(...)`
   row BEFORE the effect. All off-request code (Celery tasks, engines) binds the tenant explicitly
   (the lesson from Modules 2–8). Reuse the foundation; never reinvent it.

4. **Commit, do NOT push.** After a module is green: append its section to `docs/BUILD_NOTES.md`
   (what was built, files, new test count, key decisions, known risks, what later modules need), then
   `git add -A && git commit -m "Module X — <name> complete"`. **Never `git push`** — Hari reviews and
   pushes in the morning. Keep runtime artifacts out of git (the existing `.gitignore` already covers
   `celerybeat-schedule*`, `.DS_Store`, etc. — verify nothing stray is staged).

5. **If a module cannot reach green** after genuine, repeated effort (not one failed run — actually try
   to fix it): **STOP.** Do NOT proceed to the next module. Write `BLOCKER_<module>.md` at repo root
   describing exactly what failed, the error, what you tried, and what you need from Hari. Leave ALL
   prior modules green and committed. Then write `MORNING_REPORT.md` (rule 7) and end.

6. **If you need a human decision** (a business rule not covered here, a real API key / provider choice,
   a genuine ambiguity): write `NEEDS_HARI_<topic>.md` at repo root stating the question, the options,
   and **the safe default you chose to proceed with**, then CONTINUE using that safe default. Only treat
   it as a blocker (rule 5) if you genuinely cannot proceed without the answer.

7. **At the end of the run** (all modules done, OR you stopped/blocked, OR you sense you are running low
   on capacity), write `MORNING_REPORT.md` at repo root:
   - Modules completed tonight + the running test count after each.
   - Every commit hash + message you created.
   - Every `NEEDS_HARI_*.md` and `BLOCKER_*.md` file you wrote, with a one-line summary of each.
   - What is left in the build order and your recommended next step.
   - Any decision you made that Hari should sanity-check.
   Finish each module's terminal output with the standard line: `Module X complete. Tests passing.`

8. **Scope ceiling for tonight:** do NOT build Module 13 (the React frontend) or Module 14 (QA sweep /
   handoff) — they are out of scope for an unattended run (frontend is large + subjective; QA depends on
   the frontend). If you somehow complete M10 with capacity to spare, instead spend it HARDENING: add
   missing edge-case tests, tighten any thin spots you noticed, and write a `FRONTEND_READINESS.md`
   inventory of every API endpoint the frontend will consume (path, method, capability, scope, payload
   shape) — that is genuinely useful and low-risk. Do not start React.

9. **Reuse, integrate, don't fork.** Every module below plugs into things already built: the approval
   engine (M5 registry), the HITL discipline (M3), the anonymisation layer (M4), the cache framework
   (1.5a), the entitlement gate (M1), `CycleScore` (M2), the org tree (M7), the succession readiness
   math (M8). Use them. The AI agents in M10 fill the loud provider seams already left in M2/M3/M4/M6/M8.

10. **Provider/credential policy for tonight (critical):** you have NO real LLM API key, Jira creds, or
    Slack creds, and you must not require them. Everything external is built BEHIND CONFIG and defaults
    to the existing NotConfigured behaviour (loud 503 / no-op). Full pipelines are exercised in TESTS via
    deterministic in-repo FAKE providers/clients (the pattern M4 and M6 already used). No real network
    calls, ever, in code paths that run tonight. This means M10 and M12 are fully buildable and testable
    with zero external dependencies; a real key just flips a setting later.

---

## MODULE 9 — Career Development (Roadmap LITE)  [Doc 2 §Module 10]

Read `docs/Document_2_..._Specification.md` §Module 10 (Career Development) + §AI Agents → Career Roadmap
LITE (node sequence) + §2 + §3. Advisory-only, **never auto-promotion**. Reuses the Module-8 succession
readiness math but MUST NOT expose succession's sensitive surface to employees.

**SCOPE — IN:** target-role selection, deterministic skill-gap computation, a deterministic advisory
development roadmap, progress tracking, the Career-Roadmap-LITE provider SEAM.
**SCOPE — OUT (loud seam + comment):** the actual LLM roadmap drafting (Module 10), the Fast-AI "what
should I focus on next" suggestion (Module 10). No auto-promotion logic anywhere.

**LOCKED DECISIONS:**
1. `apps/career` — new app. Models (TenantScopedModel):
   - `TargetRoleSelection`: employee (User), target (link to a PUBLISHED `jd.JobDescription` OR an
     `org.Position` as the role profile — accept either via a nullable FK pair; require exactly one),
     selected_at, selected_by.
   - `DevelopmentRoadmap`: employee, target, status {DRAFT, ACTIVE, ARCHIVED}, tiers (JSON — ordered
     development tiers), source {DETERMINISTIC, AI}, advisory (bool, ALWAYS True), confidence_score
     (nullable — AI), generated_at, generated_by. Unique (tenant, employee, target) active row.
   - `RoadmapProgress`: roadmap FK, tier_index, status {NOT_STARTED, IN_PROGRESS, DONE}, updated_by.
2. Deterministic engine (`apps/career/engine.py`): compute the skill gap by REUSING the Module-8
   readiness math for THIS employee against the target role's required band — i.e. import the succession
   readiness/performance-band computation (from `CycleScore`) and derive a gap = required band − current
   band, plus weak KPI/goal categories from Module 2. Produce a deterministic tiered path (e.g. "reach
   MEDIUM sustained performance", "close KPI gap in <category>", "complete a stretch goal"). Pure,
   reproducible, ungated. **Data boundary:** career reuses the readiness COMPUTATION only — it must NEVER
   surface succession bench/9-box/coverage/other employees to the viewer; an employee sees only THEIR OWN
   roadmap and gap.
3. Career-Roadmap SEAM (Module 10): `apps/career/roadmap_agent.py`: `CareerRoadmapProvider` (ABC) +
   `NotConfiguredProvider` (raises tested `CareerRoadmapNotConfiguredError`) + `get_provider()` resolving
   `settings.CAREER_ROADMAP_PROVIDER`. `apps/career/tasks.py::generate_roadmap(tenant_id, employee_id,
   target_ref, actor_id)`: bind tenant; compute the deterministic gap (always); resolve provider —
   NotConfigured → return `{"generated": false, "reason": "no_provider"}` with the DETERMINISTIC roadmap
   intact (endpoint 503 for the AI-enriched variant; the deterministic roadmap is the working baseline).
4. RBAC keys: `select_target_role` (Employee OWN; Manager/HRBP for reports/BU), `view_career_roadmap`
   (Employee OWN; Manager reports TEAM; HRBP TENANT), `manage_career_roadmap` (generate/regenerate —
   Employee own OR Manager for reports). Employees DO see their own roadmap (unlike succession).
5. API (`apps/career`, RBAC-gated + audited): select target role, get/regenerate own roadmap, skill-gap
   detail, update progress, scoped list for managers/HRBP. Audit before effect.

**TESTS (exhaustive):** deterministic gap correctness from `CycleScore` bands; advisory flag always True;
the data boundary (career roadmap NEVER leaks succession bench/9-box or other employees); employee sees
own only, manager sees reports, HRBP tenant, cross-tenant 404; the seam returns 503 with the deterministic
roadmap intact; progress tracking; isolation + off-request tenant binding.

**DoD live demo:** an employee selects a target role → deterministic skill-gap + tiered roadmap returned;
the AI-enrich endpoint → 503 with the deterministic roadmap intact; a manager views a report's roadmap;
an employee CANNOT see another employee's roadmap or any succession data (404); cross-tenant 404.

**Then:** full suite green (existing 792 + new) → BUILD_NOTES → commit `Module 9 — Career Development complete`.

---

## MODULE 11 — Entitlements, Billing & Admin (+ Audit Console)  [Doc 2 §Module 13 + §Module 14 console]

Read §Module 13 (Admin & Billing — the AI-upgrade-switch diagram) + §Module 14 (Audit Log — the console)
+ §2 + §3. Completes the decoupled commercial model (seat_count × feature_packs) started in Module 1,
adds usage metering + agent budgets that Module 10 will write to, and adds the searchable audit console.
Deterministic, AI-free (the "which packs would help" advisory is a Module-10 seam).

**SCOPE — IN:** tenant config, user/role management (Admin), full entitlement management + the AI upgrade
switch, feature flags surfaced at the API, a `TokenLedger` usage meter, per-tenant agent-call budgets
tied to entitlements, and the audit console (searchable read API). 
**SCOPE — OUT (seam/Phase 2):** live payment gateway (entitlements are demoable without it — Phase 2);
the "which packs would help this tenant" advisory (Module 10).

**LOCKED DECISIONS:**
1. `apps/billing` (extend) + `apps/admin` (new, for tenant/user/role config) — or keep all in `apps/billing`
   if cleaner. Models (TenantScopedModel where applicable):
   - Extend the existing `Entitlement` with explicit feature-flag resolution: a service
     `feature_flags_for(tenant_id) -> {flag: bool}` covering every gated feature (agent1..agent4,
     jd_generator, career_roadmap, chat, etc.), derived from seat_count × feature_packs. Cache it with
     the existing `tenant_cache_key` (300s) and invalidate on any entitlement change (reuse the M1 pattern).
   - `TokenLedger` (TenantScopedModel): tenant, agent_code, model, prompt_tokens, completion_tokens,
     total_tokens, occurred_at. The meter the M10 LLMGateway will write to. Build the model + a
     `record_usage(...)` service now.
   - `AgentBudget` (TenantScopedModel): tenant, agent_code (or "all"), window {DAILY, MONTHLY}, limit,
     derived-from-entitlement defaults (STARTER lower than FULL_AI). A service
     `check_and_reserve_budget(tenant_id, agent_code)` (Redis counter per tenant:agent:window, checked
     BEFORE an agent runs; over budget → a clear 429-style error with an upgrade hint). M10 calls this
     before enqueuing/running an agent. EVERY counter key embeds tenant_id (cross-tenant isolation).
2. The AI upgrade switch (complete Module 1's `upgrade_to_full_ai`): pack add/remove, `set_seats`,
   instant feature-flag flip (locked agents unlock with no seat change), all audited, cache invalidated,
   Admin-only. Match the Doc-2 upgrade diagram. Provide an in-app "upgrade prompt" data endpoint (what's
   locked + what unlocking costs conceptually — no real pricing/payment).
3. Tenant config + user/role management (Admin-only): create/deactivate users, assign roles, set the
   reporting line (reuse the M7 `reassign_reporting_line` with its cycle check — do NOT duplicate it),
   tenant settings. All audited. (Creating a user that authenticates is fine; do NOT implement payment
   credential capture — Phase 2.)
4. Audit Console (fills Doc 2 §Module 14): a searchable, paginated, READ-ONLY API over `AuditLog`,
   filterable by actor / action / date-range / target, scoped — HRBP scoped read, Admin tenant read,
   **nobody can write/alter** (the M1 immutability already guarantees this; the console is read-only).
5. RBAC keys: `manage_tenant_config`, `manage_users_roles`, `manage_entitlements` (Admin),
   `view_audit_console` (HRBP scoped, Admin tenant). Reuse existing billing capabilities where present.

**TESTS (exhaustive):** seat_count ↔ feature_packs stay independent; the upgrade switch flips flags
instantly without changing seats (audited, cache invalidated); `feature_flags_for` matches packs;
`check_and_reserve_budget` trips at the limit and isolates per tenant; `record_usage` writes ledger rows;
user/role management audited + Admin-only; the audit console is searchable, scoped, and READ-ONLY (a write
attempt is impossible — re-prove against the M1 immutability); cross-tenant isolation throughout.

**DoD live demo:** a STARTER tenant has agents 3–5 locked (`feature_flags_for` shows them false); Admin
upgrades to FULL_AI → flags flip instantly, seats unchanged, audited; an agent budget trips at its limit
(per-tenant); an Admin creates a user + assigns a role (audited); the audit console returns filtered,
scoped, read-only results; a non-Admin is 403 on config; cross-tenant 404.

**Then:** full suite green → BUILD_NOTES → commit `Module 11 — Entitlements, Billing & Admin complete`.

---

## MODULE A — Analytics & Reporting  [Doc 2 §Module 12]  ⚠️ SCOPE-FLAG

> **FIRST:** write `NEEDS_HARI_analytics_scope.md` noting that Analytics is ✅ MVP in Doc 2 §Module 12 but
> is NOT listed in CLAUDE.md's 14-step build order, and that you are building it tonight because it is
> deterministic, MVP-marked, and builds only on completed modules — Hari to confirm it belongs in MVP
> scope. Then build it.

Read §Module 12 (the min-cohort-suppression diagram) + §2 + §3. Deterministic. The Fast-AI at-risk
rollup / anomaly highlight is a Module-10 seam; the department-health narrative is Phase 2.

**LOCKED DECISIONS:**
1. `apps/analytics` — likely NO new persisted models (aggregates are computed from `CycleScore` (M2),
   feedback (M4), 9-box (M8)); add small cache-backed aggregation services. If a snapshot is needed for
   performance, a `DepartmentAggregate` cache row is acceptable but prefer computed + cached via
   `tenant_cache_key`.
2. **MIN-COHORT SUPPRESSION = cohort size ≥ 5** (per the Doc-2 diagram — NOTE this is a DIFFERENT, separate
   threshold from the Module-4 feedback per-group min-volume of 3; keep both, document the distinction).
   Any department/cohort view with < 5 members SUPPRESSES individual values and returns aggregate-only (or
   a "cohort too small" marker) — small teams can never be de-anonymised. This is the headline safety
   property; prove it with a test (a 4-person dept exposes no individual values; a 5-person dept does).
3. Surfaces: individual performance analytics (own trend), department rollups (cohort aggregates),
   9-box calibration grid data (reuse M8 placements), export (text/JSON only — no binary).
4. RBAC keys: `view_individual_analytics` (Employee OWN; Manager reports; HRBP/Admin tenant),
   `view_department_analytics` (Manager reporting line; HRBP/Admin tenant — never Employee),
   `view_calibration_grid` (HRBP/Admin). Min-cohort suppression applies on top of scope.
5. At-risk-rollup / anomaly SEAM → Module 10 (advisory, read-only; build only the seam if trivial, else
   just note it).

**TESTS:** min-cohort suppression at the 5 boundary (4 suppressed, 5 exposed); scope tiers; calibration
grid reuses 9-box correctly; export scoped; cross-tenant isolation; cache correctness + invalidation.

**DoD live demo:** a 4-person department → individual values suppressed, aggregate-only; a 5-person
department → full metrics; a manager sees only their line; an employee sees only their own individual
analytics (and is 403/404 on department analytics); the calibration grid renders 9-box data for HRBP;
cross-tenant 404.

**Then:** full suite green → BUILD_NOTES → commit `Module A — Analytics & Reporting complete`.

---

## MODULE 12 — Integrations: Jira + Slack  [build-order Module 12]

Read §Module 3 (the Jira actual-value seam in Goals) + the Slack notification touchpoints (KPI nudges,
approval inbox/escalations, feedback requests) + §2 + §3. Fills the real provider/client behind the seams
left in M2/M4/M5. **No real Jira/Slack credentials — everything behind per-tenant config, tested with fake
clients, unconfigured = the existing no-op/NotConfigured behaviour.**

**LOCKED DECISIONS:**
1. `apps/integrations` — new app. Model (TenantScopedModel): `TenantIntegration`: tenant, kind {JIRA,
   SLACK}, enabled (bool), config (JSON — base_url, project, channel, etc.), and a secret reference.
   **Secrets:** do NOT store raw tokens in plaintext columns; read them from env per tenant
   (`<KIND>_TOKEN_<TENANTSLUG>` convention) OR an encrypted field — and write `NEEDS_HARI_secrets.md`
   recommending a proper secrets store (e.g. KMS/Vault) for production. Unconfigured/disabled tenant →
   the integration is a clean no-op.
2. **Jira** (fills `apps.goals.jira.get_provider` via `settings.JIRA_ACTUAL_PROVIDER`): a real
   `JiraActualProvider` that, for KPIs with `source=JIRA`, fetches the actual value via the Jira REST API
   using a thin HTTP client. The HTTP client is injectable so tests use a FAKE returning canned issues;
   no real network call in tests. `sync_jira_actuals` writes actuals through the EXISTING
   `record_actual(...)` path. Unconfigured → the M2 log-and-skip behaviour, unchanged.
3. **Slack** (fills the notification touchpoints): a `SlackNotifier` behind config that posts to a tenant
   channel/webhook. Wire it to: KPI nudges (the Agent-2 surface — guard so it works once M10 lands),
   approval inbox assignments + escalations (M5), feedback requests (M4). The notifier is injectable;
   tests use a FAKE recording sends; unconfigured tenant → no-op (logged). Notifications are best-effort:
   a Slack failure NEVER breaks the underlying action (wrap + log).
4. RBAC keys: `manage_integrations` (Admin — configure/enable per tenant). Reads/sends are system-driven,
   not user endpoints (except the config CRUD).
5. Off-request: the Jira sync task and any Slack send from a task bind the tenant explicitly.

**TESTS:** Jira sync with a FAKE client writes actuals via `record_actual`; unconfigured Jira → log-and-skip
(M2 behaviour preserved); Slack notifier with a FAKE records the expected message; a Slack send failure does
NOT break the triggering action (approval still completes, etc.); per-tenant config isolation; secrets never
logged; `manage_integrations` Admin-only; cross-tenant isolation.

**DoD live demo:** configure a tenant's Jira (fake client) → a JIRA-sourced KPI's actual is pulled and
recorded → the Module-2 scoring reflects it; configure Slack (fake) → an approval assignment + an escalation
+ a feedback request each produce a recorded notification; an unconfigured tenant → clean no-op (no crash);
a forced Slack failure leaves the approval intact; cross-tenant config isolation.

**Then:** full suite green → BUILD_NOTES → commit `Module 12 — Integrations (Jira + Slack) complete`.

---

## MODULE 10 — AI Agents via LangGraph + LLM Gateway  [build-order Module 10] — BUILD LAST, CAREFULLY

> This is the biggest and highest-value module and the one most likely to consume the rest of the night.
> Build it AGENT BY AGENT, each independently tested (with a deterministic FakeProvider) and **committed
> separately** so partial progress is never lost. If you run low on capacity mid-module, STOP cleanly:
> whatever agents are done stay green + committed, write `MORNING_REPORT.md` listing which agents are done
> and which remain. **No real LLM key is required or used** — providers are flagged off; the full graphs
> are exercised via a FakeProvider in tests; production stays on NotConfigured (loud 503) until Hari adds a
> key and picks a provider.

Read §AI Agents (Part B — every agent's LangGraph node sequence: Agent 1 Review, Agent 2 KPI, Agent 3
Feedback, Agent 4 Succession, JD Generator, Career Roadmap, Chat Assistant) + §Module 11 (Chat) + Doc 3 §5
(the shared Large-AI safeguard pipeline) + §2 + §3. Honour CLAUDE.md rule 6: **ALL LLM calls go through
`LLMGateway` only — never a direct SDK call.** Honour rule 4: every consequential agent output is locked
`PENDING_HUMAN_REVIEW` and audited before approval.

**LOCKED DECISIONS:**
1. `apps/ai` (or `apps/llm`) — the orchestration core:
   - `LLMGateway`: the single choke for all LLM calls. Resolves a provider from `settings.LLM_PROVIDER`
     (provider-agnostic per CLAUDE.md). Responsibilities on EVERY call: enforce the per-tenant agent budget
     (`apps.billing.check_and_reserve_budget` from M11) BEFORE the call; PII-scrub inputs; validate the
     LLM output against the agent's schema; record usage to the `TokenLedger` (M11); attach a confidence
     score; surface errors as structured results (never raw exceptions to the caller).
   - Provider layer: a `LLMProvider` ABC; a `NotConfiguredProvider` default (raises → agents 503 in prod);
     a deterministic in-repo `FakeLLMProvider` for TESTS (returns schema-valid structured output so full
     graphs run without a network call); and a thin real adapter scaffold (e.g. an OpenAI-compatible
     `HTTPLLMProvider` reading base-url + key from env) that is INERT without a key. No real call tonight.
   - LangSmith tracing wired behind env (`LANGSMITH_API_KEY`); a no-op when unset.
2. LangGraph graphs, each plugging into its EXISTING seam (point the seam's provider import-string at the
   new LangGraph-backed provider; the gateway underneath is NotConfigured in prod, FakeLLMProvider in tests):
   - **Agent 1 — Review Assistant (Large):** nodes = validate input schema → gather KPIs/goals/feedback
     (tenant-scoped, M2) → scrub PII → validate evidence sufficiency → LLM drafts 5 sections → structure to
     contract → confidence + citations → if confidence < 0.70 attach a yellow warning (still a draft) →
     lock `PENDING_HUMAN_REVIEW` via the M3 state machine → audit. Fills `apps.reviews` ReviewAssistantProvider.
   - **Agent 2 — KPI Intelligence (Fast):** weekly Celery-beat trigger → read KPI trajectory (M2) →
     classify risk → nudge rules (on-track → null; at-risk AND days_remaining ≤ 14 → suppress + warning;
     worsening → CRITICAL nudge; else → standard nudge) → surface to the manager dashboard + Slack (M12).
     Subscribes to / complements the M2 `cycle_scores_recomputed` signal. Never auto-changes data.
   - **Agent 3 — Feedback Summarization (Large):** consumes the M4 ANONYMISED payload (never raw givers) →
     LLM 4-section theme summary → **post-LLM anonymity-breach check (now load-bearing — the M4 pre-LLM
     guard is email-only; this catches free-text name leaks)** → lock `PENDING_HUMAN_REVIEW` → HRBP/sensitivity
     gate (M4). Fills `apps.feedback` FeedbackSummarizerProvider.
   - **Agent 4 — Successor Planning (Large):** internal `CycleScore`/goals (M2) + ANONYMISED 360 (M4) →
     enriched readiness/ranking/narrative/red-flags → a new `source=AI` SuccessionPlan locked PENDING for
     HRBP re-review (M8). Fills `apps.succession` SuccessionAnalyzerProvider.
   - **JD Generator (Large):** validated inputs (M6) → LLM JD body → structure → lock PENDING (M6). Fills
     `apps.jd` JDGeneratorProvider. ADD the `jd_generator` feature code to the FULL_AI pack (M11) and gate
     the surface with `requires_entitlement("jd_generator")`.
   - **Career Roadmap LITE (Large):** deterministic gap (M9) + LLM tiered path → advisory roadmap (never
     auto-promotion). Fills `apps.career` CareerRoadmapProvider.
   - **Chat Assistant (Fast, READ-ONLY, the safety-critical one):** NL query → interpret intent → translate
     to a call against the EXISTING scoped service layer **using the caller's identity and RBAC** → return
     the answer. It MUST inherit the caller's exact permissions and can NEVER surface data the caller
     couldn't already see (re-use the scoped services from M2/M7/etc.; never bypass `WithinScope`). Any
     write/approval intent is BLOCKED (Phase 2). Prove with a test that the chat assistant returns 404/empty
     for data outside the caller's scope — identical to a direct API call.
3. Entitlement gates: attach `requires_entitlement(...)` to each agent surface using M11
   (Agent 2 + Chat available in STARTER per the pack registry; Agents 1/3/4, JD, Career → FULL_AI).
4. Per-agent commit: after each agent is built + green (with FakeLLMProvider) + its entitlement gate wired,
   commit `Module 10 — Agent <N>/<name> complete` so progress is durable. The umbrella commit when all are
   done: `Module 10 — AI Agents (LangGraph + LLM Gateway) complete`.
5. Write `NEEDS_HARI_llm_provider.md`: to actually RUN the agents, Hari must (a) pick a provider (the
   pending OpenAI/Gemini/Bedrock decision), (b) set the key + `LLM_PROVIDER` setting, (c) confirm the
   per-tenant agent budgets. Until then production stays on NotConfigured (503) — by design.

**TESTS (exhaustive, all via FakeLLMProvider — no network):** each graph end-to-end (schema-validate →
PII-scrub → evidence → LLM node → structure → confidence → HITL lock → audit); confidence < 0.70 attaches a
warning but still locks PENDING (Agent 1); Agent 2 nudge rules incl. the ≤14-days suppression and Slack
surfacing (M12 fake); Agent 3 post-LLM breach check catches a free-text name leak the M4 email guard missed
→ HRBP_HOLD; Agent 4 enriches into a new source=AI PENDING plan without touching the deterministic one and
NEVER pulls raw 360; JD/Career fill their seams and lock PENDING; **Chat inherits caller RBAC — returns
nothing the caller couldn't see, write intents blocked**; the LLMGateway records `TokenLedger` usage and
enforces the agent budget before calling; NotConfigured provider → 503 everywhere (no fabricated content);
every consequential output is audited before effect; cross-tenant isolation; all off-request graphs bind
the tenant.

**DoD live demo (with the FakeLLMProvider configured in the demo env only, never a real key):** trigger
Agent 1 → a 5-section draft locked PENDING with confidence + citations → manager approves (HITL) →
finalised; Agent 2 weekly run → a CRITICAL nudge surfaced + a ≤14-day suppression case; Agent 3 → an
anonymised 4-section summary, and a planted free-text name leak → HRBP_HOLD; Agent 4 → a source=AI
succession plan PENDING with the deterministic one intact; JD generate → PENDING draft; Career → advisory
roadmap; Chat → "show me <out-of-scope person>'s goals" returns nothing (RBAC-bound), a write request
blocked; the TokenLedger shows recorded usage; with the provider unset → every agent surfaces 503;
cross-tenant isolation throughout.

**Then:** full suite green → BUILD_NOTES → final commit `Module 10 — AI Agents (LangGraph + LLM Gateway) complete`.

---

## END OF RUN

After M10 (or wherever you stopped), write `MORNING_REPORT.md` per rule 7. If you completed everything with
capacity to spare, do the HARDENING + `FRONTEND_READINESS.md` work from rule 8 — but do NOT start the React
frontend (Module 13) or the QA/handoff sweep (Module 14). Leave the working tree clean and every completed
module committed locally (NOT pushed). Good night — Hari reviews in the morning.

---

## QUICK VALIDATION CHECKLIST (apply to EVERY module before its commit)
- [ ] Full test suite green on MySQL in Docker (record the new total).
- [ ] Every new model inherits `TenantScopedModel`; cross-tenant read/write impossible (tested).
- [ ] Every endpoint RBAC-gated; new capability keys in `matrix.py` + oracle test extended.
- [ ] Every consequential action audited BEFORE effect.
- [ ] All off-request code binds the tenant explicitly.
- [ ] No placeholders / TODOs / fabricated content; seams are loud (503/no-op), never fake output.
- [ ] External calls behind config; tests use fakes; no real network/credentials used.
- [ ] BUILD_NOTES.md section appended; committed locally with the standard message; NOT pushed.
- [ ] Nothing stray staged (runtime artifacts gitignored).
