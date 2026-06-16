# Architecture Map — Talbotiq PMS

> **Purpose.** The domain model, business hierarchy, role/scope model, tenancy,
> the AI-agent pipeline + HITL gates, and the information architecture — the
> mental model a designer, engineer, PM, or new dev needs before touching the UI.
> **Grounding.** Derived from the real backend (`apps/*/models.py`,
> `serializers.py`, `urls.py`, `apps/rbac/matrix.py` + `scope.py`) and the
> existing `docs/frontend-contract/*`. This is one of five redesign docs; see
> `frontend-spec.md`, `screen-inventory.md`, `user-workflows.md`, `ux-spec.md`.
> Where this **corrects** the contract against the real code, it is flagged
> **⚠ DRIFT**.

---

## 1. The product in one paragraph

Talbotiq PMS is a **multi-tenant, RBAC, AI-assisted performance-management system**
for the SME market. Each tenant (company) runs the full performance lifecycle:
**Goals & KPIs → Reviews → 360° Feedback → Approvals → JD library → Org chart →
Succession → Career development → Analytics**, with **AI agents** assisting at
every drafting point and a **human-in-the-loop (HITL) gate** on every AI/automated
output. Two product surfaces share one API: a **desktop Admin Hub** (management +
configuration) and a **mobile self-service** surface (employee/manager own-work,
planned — see `MOBILE_BUILD_PLAN.md`).

---

## 2. Foundational architecture (non-negotiable — from CLAUDE.md)

These shape every screen and must never be weakened in the UI:

1. **Tenant isolation.** Every model is `TenantScopedModel` (UUID pk + `tenant` FK);
   a `TenantScopedManager` filters every query by tenant. The JWT carries
   `tenant_id` — **the frontend never sends a tenant id**; a cross-tenant row is a
   **404**, never a 403 (never reveal it exists elsewhere).
2. **RBAC, server-side, on every endpoint.** The frontend is never trusted; it gates
   UI for UX (hide what a role can't do) but the server is the only authority.
3. **JWT** embeds `tenant_id` + `role` + `email` on every request.
4. **Every AI output is locked PENDING_HUMAN_REVIEW** (or an equivalent draft/hold)
   until a human acts — the HITL gate is always present.
5. **AuditLog is INSERT-only** at the DB level — no UPDATE, no DELETE, ever. The
   audit console therefore has **no mutation controls**.
6. **All LLM calls go through the single `LLMGateway`** — never a direct SDK call.

---

## 3. The role model + data scope

Four roles, increasing breadth. **Capability** (what a role may *do*, `matrix.py`)
is separate from **scope** (what data it may *see*, `scope.py`).

| Role | Scope | In one line |
|------|-------|-------------|
| **EMPLOYEE** | OWN | Own data only — own goals/actuals, own review (read), own 360 (give + own released summary), own career roadmap, chat. |
| **MANAGER** | TEAM (reporting subtree + self) | Everything an employee has, **plus** manage their reports: reviews, goal approval, team analytics, 360 cycles, own-tier succession/bench, approvals inbox. |
| **HRBP** | TENANT | Business-unit/tenant-wide talent governance: feedback-summary release, succession generate/publish, calibration grid, audit console (read). |
| **ADMIN** | TENANT | Full tenant control: users/roles, tenant config, entitlements/billing, integrations, approval-workflow design — **plus** everything above. |

Scope is enforced in services, not the UI. Two capabilities are held by **nobody**
(structural guarantees): `bypass_tenant_isolation` and `alter_audit_log`.

**Scope resolution (`scope.py`):** `OWN` → self only; `TEAM` → `reporting_subtree_ids
(user) ∪ {self}`; `TENANT` → the whole active tenant. `actor_can_access(actor,
subject)` is the single gate used everywhere; out-of-scope → 404.

---

## 4. The domain entities (the business hierarchy)

Grouped by module. For each: purpose · key fields · lifecycle/states · the business
rules a designer must respect. (Exact serializer field lists are in
`frontend-spec.md`.)

### 4.1 Identity & tenancy
- **Tenant** — the company. `slug` (login hint), `name`, `status` (ACTIVE/…). The
  unit of isolation. **Entitlement** (below) hangs off it.
- **User** — `email` (unique *per tenant*), `role`, `manager` (FK → reporting line),
  `is_active`, `mfa_enabled`, **`display_name`** (optional) + a computed **`display`**
  (= display_name or email). Login is **tenant-qualified** (email + password + tenant
  slug). ⚠ DRIFT: `GET /api/auth/me` now also returns **`tenant_name` + `tenant_slug`**
  (added this run) — contract 01 listed only `{id,email,role,tenant,mfa_enabled}`.

### 4.2 Goals & KPIs (Module 2) — the performance substrate
- **PerformanceCycle** — a review period (`name`, `start_date`, `end_date`, `status`
  ACTIVE/…). Goals/reviews/scores hang off a cycle. Cycle CRUD is HRBP/Admin.
- **Goal** — an employee's weighted objective in a cycle. `title`, `description`,
  `objective`, **`weight`** (Decimal), `status` (DRAFT→ACTIVE→ACHIEVED/MISSED/
  ARCHIVED), `approved_by/at`. **Rule:** an employee's **ACTIVE goal weights must sum
  to exactly 100.00**.
- **Kpi** (under a Goal) — `name`, `weight` (Decimal), `target_value` (>0),
  `direction` (INCREASING/DECREASING), `unit`, `source` (MANUAL/JIRA). **Rule:** a
  goal's **KPI weights must sum to exactly 100.00**.
- **KpiMeasurement** — append-only actuals (`value`, `recorded_at`); the latest is the
  current actual. Recording an actual is **own-only** (a peer's → 404).
- **CycleScore** (computed, read-only) — `raw_score`, `z_score`, `t_score`,
  `cohort_size`, `cohort_key`, `insufficient_cohort`, `risk_status`
  (ON_TRACK/AT_RISK/CRITICAL), `pace_behind`, `computed_at`. The engine
  (`apps/goals/scoring/engine.py`) is deterministic + reproducible (all Decimal). A
  **recompute** is idempotent over the whole cohort.
- **KpiTemplate** — role-targeted reusable KPI definitions; instantiate into real
  Goal/KPI rows.

### 4.3 Reviews (Module 3) — the appraisal lifecycle (HITL)
- **Review** — `employee`, `reviewer`, `cycle`, **`state`** (see §6.1), `draft_body`,
  `final_body`, `human_reviewer` (null until approved), `approved_at`, `finalized_at`,
  `rejected_reason`, **`source`** (MANUAL/AI), `confidence_score` + `citations` (AI
  only). **DB guarantee:** a FINALIZED review always has a `human_reviewer`.
- **ReviewAssessment** — SELF (the subject) / MANAGER / PEER / UPWARD inputs.
- **ReviewStateTransition** — the audited timeline (from/to/action/actor/at).

### 4.4 360° Feedback (Module 4) — multi-rater, anonymised (HITL)
- **FeedbackCycle** — a 360 window for ONE subject. `status` (DRAFT→COLLECTING→
  CLOSED), `min_volume` (per-group anonymity threshold, default 3).
- **FeedbackRequest** (invitation) — `giver`, `relationship` (SELF/MANAGER/PEER/
  UPWARD), `status` (PENDING/SUBMITTED/DECLINED). The invitation IS the authorization
  to give.
- **Feedback** — the sensitive item: `body`, `relationship`, `kind` (THREE_SIXTY/
  CONTINUOUS). **The `giver` is stored but NEVER egressed** except to the giver
  viewing their own.
- **Anonymised payload** (egress artifact, computed) — pseudonyms (PEER#1…), per-group
  volumes, `insufficient_groups` (PEER/UPWARD below threshold are suppressed), **zero
  giver identifiers**. PEER/UPWARD gate on min-volume; SELF/MANAGER are single-rater
  and exempt.
- **FeedbackSummary** — the Agent-3 4-section summary (`sections`
  strengths/growth/themes/risks — **NULL until Agent 3 ran**), `status`
  (PENDING_HUMAN_REVIEW/HRBP_HOLD/APPROVED/RELEASED), `anonymity_passed`, `sensitive`,
  `volume_total`, `insufficient_groups`, `confidence_score`. Released only after HRBP
  review.
- **OneOnOneNote** — private to its two participants (manager+employee); **even Admin
  is denied**; never anonymised, never summarised.

### 4.5 Approvals (Module 5) — configurable routing
- **ApprovalWorkflow** — `name`, `artifact_type` (review/jd/…), `mode` (SEQUENTIAL/
  PARALLEL), `active`. At most one ACTIVE per artifact_type. ⚠ Steps are defined **at
  create time** (no PATCH; re-create to change; in-flight routes are snapshotted).
- **ApprovalStep** (definition) — `order`, `approver_kind` (ROLE/NAMED),
  `approver_role`/`approver_user`, `required`, `timeout_hours`, `escalation_role/user`.
- **ApprovalRoute** (instance) — `status` (IN_PROGRESS/APPROVED/REJECTED/ESCALATED),
  `mode`, `initiated_by`. Completion fires the artifact callback (review→FINALIZED,
  JD→PUBLISHED).
- **ApprovalStepInstance** — `order`, `approver`, `status` (PENDING/APPROVED/REJECTED/
  ESCALATED/SKIPPED), `due_at`, `escalated`, `decided_by/at`, `comment`.

### 4.6 JD Library (Module 6) — job descriptions (HITL on AI)
- **JobDescription** — `title`, `level`, `department`, `status` (DRAFT→
  PENDING_HUMAN_REVIEW→IN_REVIEW→PUBLISHED→ARCHIVED), `source` (MANUAL/AI),
  `current_version` (the live PUBLISHED version, immutable), `approval_route`.
- **JDVersion** — `version_number`, `body` {summary, responsibilities[], must_haves[],
  nice_to_haves[]}, `confidence_score`+`citations` (AI), `is_published`.
- **JDRequest** — a Manager asks HRBP to author/generate a JD; `status` (OPEN/
  FULFILLED/DECLINED).

### 4.7 Org chart (Module 7)
- **Org tree** (computed) — nodes (user + `headcount` subtree + `vacancies`), edges,
  roots, rollups. Scoped: Employee = own line, Manager = subtree, HRBP/Admin = tenant.
- **Position** — `title`, `reports_to`, `department`, `status` (OPEN/FILLED/CLOSED),
  `filled_by`, `published_jd`. Fill/close/link-JD are HRBP/Admin. **Reassign** a
  reporting line is cycle-checked (a loop → **422 REPORTING_CYCLE**); a linked JD must
  be PUBLISHED.

### 4.8 Succession & Talent (Module 8) — MANAGEMENT-ONLY (invisible to employees)
- **CriticalRole** — `name`/position, `incumbent`, `criticality` (HIGH/CRITICAL),
  `knowledge_risk` (LOW/MEDIUM/HIGH), `status` (ACTIVE/ARCHIVED).
- **BenchCandidate** — `candidate`, `readiness` (READY_NOW/READY_SOON/DEVELOPING/
  NOT_READY), `readiness_overridden` (an HRBP override sticks; else derived).
- **NineBoxPlacement** — `performance_band` (derived from CycleScore) × `potential_band`
  (human-assigned) → box 1–9, per cycle.
- **SuccessionPlan** — `status` (DRAFT→PENDING_HUMAN_REVIEW→PUBLISHED), `ranked_bench`,
  `coverage_status` (RED/AMBER/GREEN), `red_flags`, `action_items`, `source`
  (DETERMINISTIC/AI), `confidence_score`. **The whole module returns 404 to an
  employee** — it must be absent from any employee surface.

### 4.9 Career Development (Module 9) — advisory, employee-visible
- **TargetRoleSelection** — exactly one of `target_jd` (PUBLISHED) / `target_position`;
  `selected_by/at`.
- **DevelopmentRoadmap** — `status` (DRAFT/ACTIVE/ARCHIVED), `tiers`
  [{index,title,detail,basis}], `skill_gap` {current/required performance band, band
  gap, weak_categories — **performance-derived only, never succession data**},
  `source` (DETERMINISTIC/AI), **`advisory` always true** (DB CHECK — never
  auto-promotion), `confidence_score`. ⚠ DRIFT: an AI-enriched roadmap is created as a
  **DRAFT**, but there is **no "accept → ACTIVE" endpoint** — it simply coexists
  alongside the deterministic ACTIVE roadmap (the "human acceptance" is conceptual,
  not a transition). Flag for the redesign: either add an accept endpoint or present
  the AI roadmap as an advisory alternative, not a pending activation.
- **RoadmapProgress** — per-tier `status` (NOT_STARTED/IN_PROGRESS/DONE).

### 4.10 Analytics (Module A) — deterministic, privacy-gated
- **Individual trend** — per-cycle t_score, risk_status, raw_score, pace_behind.
- **Department analytics** — `cohort_size`, `min_cohort = 5`, **`suppressed`** (bool),
  aggregate {headcount, scored, mean/median t_score, risk_distribution}, `individuals[]`
  (**empty when suppressed**). **Rule:** a department with **< 5** scored people shows
  aggregate-only (no individuals) — a privacy guarantee.
- **Calibration grid** (HRBP/Admin) — per-box counts + placements (no min-cohort
  suppression on calibration).

### 4.11 Entitlements, Billing, Admin, Integrations, Audit (Module 11/12)
- **Entitlement** — per-tenant `seat_count`, `feature_packs[]` (STARTER/FULL_AI),
  `unlocked_agents[]`, `tier_label`. Drives the feature-flag map.
- **TenantConfig** — free-form `settings{}` JSON.
- **TenantIntegration** — `kind` (JIRA/SLACK), `enabled`, `config{}`, **`secret_ref`** =
  the env-var NAME of a token (**never the token value**; never returned).
- **AuditLog** — `actor`, `action`, `target_type/id`, `justification`, `metadata`,
  `created_at`. INSERT-only; read-only console.

---

## 5. Tenancy & entitlements (the commercial layer)

- Two **packs**: **STARTER** and **FULL_AI**. The seed ships **acme = FULL_AI** and
  **globex = STARTER** for the demo contrast.
- **Feature flags** (`{feature: bool}`) gate premium surfaces: `agent1` (Review
  Assistant), `agent2` (KPI Intelligence), `agent3` (Feedback Summary), `agent4`
  (Succession), `agent5`, `jd_generator`, `career_roadmap`, `chat`.
- **Packaging:** STARTER unlocks **only `agent2` + `chat`** (the "AI taste").
  **Every generative agent (incl. Agent 1), the JD generator, and the career roadmap
  are FULL_AI (premium).**
- **Visibility model:** ⚠ DRIFT/clarified — any authenticated role reads its OWN map
  via **`GET /api/billing/my-features`** (added; the frontend's `useAuth` loads it for
  everyone). The Admin-only `GET /api/billing/feature-flags` is the same data for the
  admin billing screen. The UI must render a locked premium feature as **disabled +
  "Upgrade to unlock"** (drive the modal from `upgrade-prompt`), **never hidden**.
- **Upgrade** flips every premium flag instantly (seats unchanged); conceptual — no
  payment capture (Phase 2).

---

## 6. Lifecycles the UI must visualise + drive (state machines)

Always re-derive available actions from the entity's current status after each action
(a stale action → **409**). Badge convention: terminal/positive = APPROVED/PUBLISHED/
FINALIZED/RELEASED; in-flight = PENDING_*/IN_PROGRESS/AI_DRAFTING/EDITING; negative =
REJECTED; neutral = DRAFT/ARCHIVED.

### 6.1 Review
`DRAFT → (request-ai-draft) AI_DRAFTING → (system) PENDING_HUMAN_REVIEW`
`DRAFT/PENDING/REJECTED → (start-edit) EDITING → (submit) PENDING_HUMAN_REVIEW`
`PENDING → (approve) APPROVED → (finalize) FINALIZED` *(or enters an active review
approval route, then the route callback finalizes)*
`PENDING → (reject, reason required) REJECTED`. **HITL gate = PENDING_HUMAN_REVIEW.**

### 6.2 Approval route
SEQUENTIAL: only the lowest-order PENDING step is active (inbox shows just it).
PARALLEL: all steps PENDING; route completes when all required are approved. A reject
ends the route (REJECTED). Overdue steps escalate (beat). Decisions restricted to the
assigned approver (→ 403); out-of-order/already-decided → 409.

### 6.3 JD
`create → DRAFT (+v1)`; `DRAFT → (generate AI | submit) PENDING_HUMAN_REVIEW`;
`PENDING → (approve) PUBLISHED` *(or IN_REVIEW if a jd route is active)*; `PUBLISHED →
(revise) DRAFT (new version; published stays live+frozen)`; `any → ARCHIVED`.

### 6.4 Succession plan
`generate (deterministic) → PENDING_HUMAN_REVIEW → (add action-items) → (publish)
PUBLISHED`. `enrich (Agent 4) → a NEW source=AI plan PENDING` (the deterministic plan
is untouched). Publish only from PENDING (else 409).

### 6.5 Career roadmap
`select target → ACTIVE (DETERMINISTIC)`; `regenerate → ACTIVE (refreshed)`; `enrich →
a NEW source=AI DRAFT` (⚠ no activation endpoint — see §4.9). Per-tier progress:
NOT_STARTED↔IN_PROGRESS↔DONE.

---

## 7. The AI-agent pipeline + HITL gates

All AI flows through **one choke point**, `apps/ai/gateway.py::LLMGateway`, on every
call: **budget reserve → PII-scrub (emails) → provider call (LangSmith span) →
schema-validate → meter to TokenLedger → confidence + low-confidence flag.** It never
raises and never fabricates; with no provider it returns NOT_CONFIGURED → the surface
**503s** and the deterministic/manual path still works.

| Agent | Where it assists | Output → HITL state | Pack |
|-------|-----------------|---------------------|------|
| **Agent 1 — Review Assistant** | Review draft | review PENDING_HUMAN_REVIEW (+confidence+citations) | FULL_AI |
| **Agent 2 — KPI Intelligence** | Nudges (deterministic) + Chat | nudge tile / read-only chat answer | STARTER |
| **Agent 3 — Feedback Summary** | 360 close | summary PENDING / HRBP_HOLD (anonymity breach/sensitive) | FULL_AI |
| **Agent 4 — Succession narrative** | Plan enrich | a new source=AI plan PENDING | FULL_AI |
| **Agent 5 / JD generator** | JD generate | JD PENDING_HUMAN_REVIEW (source=AI) | FULL_AI |
| **Career roadmap agent** | Roadmap enrich | a new source=AI roadmap DRAFT | FULL_AI |

**HITL is the product's spine.** Every AI/automated artifact is a *draft* until a
human acts: review approve→finalize, feedback summary release, succession plan
publish, JD approve→publish, career roadmap (advisory). The UI must **never present a
draft as final**, must always show **provenance** (source + confidence + a
low-confidence warning < 0.70) and must always offer the **human gate** (Approve /
Reject-with-reason / Edit / Publish / Release) to the role that holds it. Output
quality was tuned this run (rich evidence + grounded prompts) — see `docs/AI_GOLIVE.md`.

**Real-time:** there are **no websockets/SSE**. AI_DRAFTING, route progress, and
summary generation complete asynchronously; the frontend **polls / refetches after
actions** (React Query). A premium redesign should make this polling feel intentional
(optimistic UI, skeletons, "generating…" affordances), not janky.

---

## 8. Information architecture

### 8.1 The two surfaces (the top-level split)
| Surface | For | Roles | Nature |
|---------|-----|-------|--------|
| **Desktop Admin Hub** | management + configuration | Manager, HRBP, Admin | multi-pane, data-dense |
| **Mobile self-service** (planned) | own-work on the go | Employee, Manager | single-task, native |

⚠ DRIFT/reality: **the built Admin Hub gates every route at `min="MANAGER"`** (the
dashboard index has no gate, so an employee sees a cockpit but no nav). So **the
employee self-service experience effectively lives only in the planned mobile surface**
today; career/feedback "own" views in the hub are reachable by Manager+ subjects only.
This is consistent with the surface split but should be stated plainly in the redesign
(don't design an employee Admin-Hub journey — design the manager+ hub and the mobile
self-service).

### 8.2 Primary navigation (desktop, current — `app/nav.ts`)
Grouped sidebar (dark), all `min="MANAGER"` unless noted:
- **Workspace:** Dashboard · Approvals · Reviews · Goals & KPIs · 360 Feedback · Org
  Chart · JD Library · Career
- **Talent Intelligence:** Succession · Analytics
- **Governance:** Audit Console (HRBP+)
- **Administration:** Users & Roles · Tenant Config · Entitlements · Integrations
  (Admin)

### 8.3 Secondary navigation patterns in use
- **Tabs within a feature** (e.g. 360 Feedback: For me / My 360 / Cycles / Summaries-
  to-release; Career: My development / My team).
- **List → detail** (JD library → JD detail; reviews list → review detail).
- **Sheets/dialogs** for focused actions (cycle management, create dialogs).
- **A global chat panel** (Topbar "Ask AI") overlaid on any screen.

### 8.4 IA observations for the redesign (detail in `ux-spec.md`)
- The nav is **flat and feature-oriented** (one item per module) — fine, but it lacks
  **wayfinding** (no breadcrumbs, no "you are here" beyond the active item) and a
  **global search / command palette**, both expected in premium enterprise SaaS.
- There is **no notifications/inbox affordance** in the shell despite rich real
  signals (approvals awaiting, feedback requests, summaries to release, nudges) — these
  live only as dashboard tiles.
- The **dashboard composes client-side** (no `/dashboard` endpoint) — a chance to make
  each role's landing a genuine "command center" rather than a tile grid.

---

## 9. What to read next
- `frontend-spec.md` — every endpoint, shape, error, and the TS data model.
- `screen-inventory.md` — each screen, its states, and EXISTS-vs-weak.
- `user-workflows.md` — the end-to-end journeys + their UX gaps.
- `ux-spec.md` — the elevation direction + the **Phase 8 critique** of the built UI.
