# V0 BRIEF — PMS "Admin Hub" (desktop)

Paste this whole file into v0. Build a **desktop web Admin Hub** for a multi-tenant
**Performance Management System**. Build it with **React + Tailwind + shadcn/ui** and
**realistic MOCK data only — NO real API calls** (a real backend is wired later). The
mock data shapes in this brief match the real API 1:1 (exact field names, exact enum
values, the real pagination envelope), so the generated UI maps cleanly onto the live
API afterward.

---

## DESIGN DIRECTION
# DESIGN DIRECTION

## Product Category

This is a premium enterprise Talent Intelligence, Succession Planning, Performance Management, and Workforce Operations platform.

Do NOT design it like a startup KPI dashboard or employee engagement app.

The primary users are:

* HRBP
* Talent Partners
* Managers
* Administrators
* Leadership Teams

The UI should feel like software used all day by HR and business operators.

---

## Visual References (Study These)

Primary references:

* Ashby — https://www.ashbyhq.com
* Rippling — https://www.rippling.com
* Lattice — https://lattice.com
* Leapsome — https://www.leapsome.com
* Betterworks — https://www.betterworks.com

Secondary references:

* Linear — https://linear.app
* Vanta — https://www.vanta.com
* Retool — https://retool.com
* Workday — https://www.workday.com
* SAP SuccessFactors — https://www.sap.com/products/hcm/successfactors.html

Use:

* Ashby for information density and tables
* Rippling for admin workflows
* Linear for polish and spacing
* Lattice and Leapsome for performance-management patterns
* Workday and SuccessFactors for enterprise HR information architecture

---

## Overall Feel

Keywords:

Enterprise
Professional
Operational
Data-Dense
Executive
Modern SaaS
Talent Intelligence
Human-Centered
Audit-Friendly

Avoid:

* Marketing website aesthetics
* Excessive gradients
* Glassmorphism
* Giant dashboard cards
* Oversized spacing
* Consumer mobile-app styling
* Bright startup colors

---

## Layout

Desktop-first.

Structure:

* Left sidebar navigation
* Top command bar
* Main content area
* Slide-over panels for details
* Drawers for editing
* Modals for confirmation flows

Prefer side panels and split views over page refreshes.

---

## Typography

Font:

* Inter

Hierarchy:

* Compact
* Enterprise-friendly
* Dense but readable

Use:

* Medium and semibold weights
* Consistent spacing rhythm
* Small labels for metadata

Avoid oversized headings.

---

## Color Palette

Base:

* Slate
* Gray
* White

Primary:

* Modern Blue

Status Colors:

* Success → Green
* Warning → Amber
* Critical → Red
* Information → Blue

AI States:

* Purple

Premium / Locked Features:

* Gold / Amber accents

Colors should be subtle and professional.

---

## Spacing & Density

Target density similar to:

* Ashby
* Linear
* Rippling

Requirements:

* Dense tables
* Compact filters
* Efficient use of screen space
* Minimal wasted whitespace

Design for users managing hundreds or thousands of records.

---

## Component Style

Use shadcn/ui components.

Patterns:

* Data tables
* Stepper timelines
* Status chips
* Side panels
* Drawer editors
* Filter bars
* Tabs
* Command palettes
* Activity feeds
* Audit logs

Avoid card-heavy layouts.

---

## Dashboard Design

Dashboard should prioritize actions.

Top sections:

1. Approval Inbox
2. KPI Nudges
3. Succession Risks
4. Team Health
5. Workflow Status
6. Quick Actions

Do not build a generic analytics dashboard.

The dashboard should answer:

* What requires action?
* What is blocked?
* What is at risk?
* What needs approval?

---

## Approval Workflow UI

Reference:

* Jira approvals
* ServiceNow approvals
* GitHub PR review flows

Display as:

* Timelines
* Steppers
* Route trackers

Show:

* Pending
* Approved
* Rejected
* Escalated
* Due dates
* SLA indicators

---

## AI Experience

AI is always an assistant.

Never present AI output as final.

For:

* PENDING_HUMAN_REVIEW
* source = AI

show:

* Draft badge
* Confidence score
* Approve
* Reject
* Edit

Low confidence (<0.70):

* Warning treatment
* Elevated visibility

Reference style:

* Notion AI review states
* GitHub Copilot review workflows

---

## Premium Feature Experience

Locked features remain visible.

Show:

* Lock icon
* Upgrade to Unlock
* Feature preview
* Disabled interactions

Never hide premium capabilities.

Reference:

* Vercel Pro features
* Linear paid features
* Notion AI upsells

---

## Succession Planning (Flagship Experience)

This is one of the most important areas of the product.

Reference:

* SAP SuccessFactors Succession
* Workday Talent Management
* TalentGuard

Create:

* Executive-ready dashboards
* Coverage indicators
* Bench strength views
* Readiness chips
* Talent risk summaries

The 9-box matrix should feel premium and interactive.

---

## Analytics

Reference:

* Lattice Analytics
* Leapsome Analytics
* Workday Reporting

Use:

* Trend charts
* Distribution charts
* Cohort summaries
* Risk visualizations

Always pair charts with supporting tables.

---

## Empty States

Professional and actionable.

Explain:

* Why there is no data
* What action can be taken

Avoid playful illustrations.

---

## Final Visual Goal

A blend of:

40% Ashby
25% Rippling
20% Linear
15% Lattice

The result should feel like a modern enterprise Talent Intelligence and Performance Management platform used by HR leaders, managers, and executives every day.


## SCOPE NOTE — desktop Admin Hub only
This is the **desktop management surface** for **Admin / HRBP / Manager**. A separate
**responsive mobile-web self-service surface** (for Employees: own goals, give 360
feedback, own review, own career roadmap) is a **FUTURE build — do NOT build it here**.
Because some concepts (auth, the user object, feature flags, chat) are shared with
that future surface, **do not bake desktop-only assumptions into shared components**
(keep an auth/session/user store and an API-client layer reusable).

## Global rules v0 must honor on EVERY screen
- **Mock everything.** Centralise mock data in a `lib/mock/` module and read screens
  from it via a tiny async `fetchMock()` that returns the JSON below after a short
  delay (so loading states are real). One swap point later replaces it with `fetch`.
- **Auth/session:** a JWT-style session holds the current user `{id, email, display,
  role}`. Route + show/hide nav by `role`. The client NEVER sends a tenant id (it's
  implicit). Provide a role-switcher in dev so the designer can preview each role.
- **Every list/detail handles ALL states:** `loading`, `empty`, `populated`, and an
  **error state per HTTP code** — `400` bad input (inline form error), `401` →
  re-login, `403` "you don't have permission" (hide the action), `404` →
  **"not found / not in your scope"** (route back to the list; never imply it exists),
  `409` "this changed — refresh" (illegal state transition), `422` domain validation
  (show `detail`, key off `code`), `429` rate/budget limit (show a cooldown using
  `Retry-After` seconds; if an `upgrade_hint` is present, show an upgrade CTA), `503`
  "AI not available yet" (a calm notice, NOT an error — the manual path still works).
- **Feature-flag locking:** premium features render **disabled with an "Upgrade to
  unlock" affordance** (NOT hidden, NOT an error). Drive this from the feature-flags
  mock. STARTER unlocks only `agent2` + `chat`; **everything else (incl. `agent1`
  Review Assistant, `agent3/4/5`, `jd_generator`, `career_roadmap`) is FULL_AI/premium.**
- **HITL (human-in-the-loop):** AI/automated outputs are **drafts** until a human
  approves. Anything with `status = PENDING_HUMAN_REVIEW` (or a draft `source = AI`)
  must show a **"Draft — pending review"** badge + the **Approve / Reject (reason) /
  Edit** affordances + the `confidence_score` (badge a low score < 0.70 as a warning).
  **Never present a draft as final.**
- **Management-only screens** (Succession, Department/Calibration analytics, Audit
  console): these are invisible to Employees. In this Admin Hub, show them only to the
  roles noted; assume the real API returns **404/403** to anyone else.
- **IDs are UUID strings; money/weight/score values are decimal STRINGS (2dp display);
  timestamps are ISO-8601** (display in the viewer's local time).

---

## 1 · What it is, who uses it, the nav

A tenant's management console. Three roles use it (gate the nav by role):

| Nav section (screen) | ADMIN | HRBP | MANAGER |
|---|---|---|---|
| Dashboard | ✓ | ✓ | ✓ |
| Approvals (inbox · tracker · designer*) | ✓ | ✓ | ✓ (designer = ✗) |
| JD Library | ✓ | ✓ | ✓ (browse) |
| Org Chart | ✓ (tenant) | ✓ (tenant) | ✓ (subtree) |
| Succession **(mgmt-only)** | ✓ | ✓ | ✓ (own tier) |
| Analytics (individual · dept · calibration) | ✓ | ✓ | ✓ (dept = own line; calibration = ✗) |
| Audit Console **(mgmt-only)** | ✓ | ✓ | ✗ |
| Admin · Users & Roles · Tenant Config | ✓ | ✗ | ✗ |
| Entitlements / Billing | ✓ | ✗ | ✗ |
| Integrations | ✓ | ✗ | ✗ |
| AI Chat (panel, always available) | ✓ | ✓ | ✓ |

\* The approval **workflow designer** is HRBP/Admin; the **inbox + route tracker** are
Manager+. Calibration grid + dept analytics + audit + admin/billing/integrations are
not shown to a plain Manager.

---

## 2 · Screens

For each: **purpose · data (fields + enum values) · actions → state change · states**.
Enum values are the exact backend values — use them verbatim in mock + UI.

### 2.1 Auth & Login + MFA
- **Purpose:** sign in; optional TOTP MFA; SSO entry.
- **Data:** session user `{id, email, display, role}` where `role ∈ EMPLOYEE ·
  MANAGER · HRBP · ADMIN`.
- **Actions:** Login (email + password + tenant slug) → tokens OR an "MFA required"
  step; Submit 6-digit TOTP → tokens; "Sign in with SSO" button (redirect placeholder);
  Logout → clear session.
- **States:** login form · invalid credentials (401, generic message) · MFA-required →
  TOTP entry · MFA invalid · SSO redirecting · authenticated (route by role). Validation:
  email format, password present, TOTP = 6 digits.

### 2.2 Admin Dashboard (shell + tiles)
- **Purpose:** role landing; the app shell (top nav + role-gated sections above) wraps
  every screen. Tiles compose from feature screens.
- **Tiles to render:** Approvals inbox count; **KPI-nudges tile** (see §2.13);
  Succession coverage summary (mgmt); "what's locked" upsell tile (from feature-flags);
  quick links. Gate premium tiles via feature flags.
- **States:** loading · populated · empty (new tenant). No single dashboard endpoint —
  compose from the per-screen mocks.

### 2.3 Admin · Users & Roles  *(ADMIN only)*
- **Purpose:** manage tenant users.
- **Data (User):** `id`, `email`, `display_name` (string|null), `display` (effective
  name — **render this**), `role`, `manager` (UUID|null), `is_active` (bool),
  `mfa_enabled` (bool).
- **Actions → change:** Create user `{email, role, manager?, display_name?, password?}`
  → row added; Set role; Deactivate / Reactivate (`is_active`); Set reporting line
  (manager) → may **422 REPORTING_CYCLE**; Set display name (blank clears → email
  fallback).
- **States:** list (plain array — NOT paginated) · create form · 422 `EMAIL_TAKEN` /
  `UNKNOWN_ROLE` / `REPORTING_CYCLE` · 404 (cross-tenant id) · 403 (non-Admin).

### 2.4 Admin · Tenant Config  *(ADMIN only)*
- **Purpose:** edit tenant-level settings (free-form JSON `settings`).
- **Actions:** GET current config; PUT replace `settings` object.
- **States:** loaded · editing · saved · 403 (non-Admin).

### 2.5 Entitlements / Billing + Upgrade  *(ADMIN only)*
- **Purpose:** see the plan, flip premium on, edit seats.
- **Data:** Entitlement `{seat_count (int), feature_packs ([STARTER|FULL_AI]),
  unlocked_agents ([..]), tier_label ("Starter"|"Full AI" — DISPLAY ONLY)}`;
  feature-flags map `{feature: bool}` over `agent1..agent5, chat, jd_generator,
  career_roadmap`; upgrade-prompt `{current_packs, tier_label, feature_flags,
  locked_features[], upgrade:{pack:"FULL_AI", would_unlock[], note}}`.
- **Actions → change:** Set seats (independent of packs); **Upgrade to FULL_AI**
  (flips every premium flag instantly, seats unchanged) → show before/after; open the
  **Upgrade modal** from the upgrade-prompt (list `would_unlock`; **conceptual — NO
  pricing / payment**).
- **States:** STARTER (premium list locked) · FULL_AI (all unlocked) · seats editor
  (≥0 integer) · upgrade modal · 403 (non-Admin).

### 2.6 Approvals — Inbox · Route Tracker · Workflow Designer
- **Purpose:** act on approval steps assigned to you; watch a route; (HRBP/Admin)
  design workflows.
- **Data:** ApprovalWorkflow `{name, artifact_type ("review"|"jd"|…), mode
  (SEQUENTIAL|PARALLEL), active}`; ApprovalStep `{order, approver_kind (ROLE|NAMED),
  approver_role, approver_user, required, timeout_hours, escalation_role/user}`;
  ApprovalRoute `{status (IN_PROGRESS|APPROVED|REJECTED|ESCALATED), mode,
  artifact_type, artifact_id, initiated_by}`; ApprovalStepInstance `{order, approver,
  approver_role, status (PENDING|APPROVED|REJECTED|ESCALATED|SKIPPED), due_at,
  escalated (bool), decided_by, decided_at, comment}`.
- **Actions → change:** Approve step → advances the route (SEQUENTIAL: next step
  becomes active; last → route APPROVED) ; Reject step (comment) → route REJECTED;
  Activate / deactivate a workflow (designer).
- **States:** inbox empty vs items (SEQUENTIAL surfaces ONLY the active step) · route
  tracker = **stepper/timeline** (per-step status, due_at, `escalated` badge) · 409
  out-of-order/already-decided (refresh) · 403 not-the-assignee. Designer: list of
  workflows (array), at-most-one ACTIVE per artifact_type; **editing steps =
  re-create the workflow** (no in-place step PATCH).

### 2.7 JD Library — Browse · Editor · Version History · Requests
- **Purpose:** author + manage Job Descriptions (versioned, HITL, optional AI generate).
- **Data:** JobDescription `{id, title, level, department, status (DRAFT|
  PENDING_HUMAN_REVIEW|IN_REVIEW|PUBLISHED|ARCHIVED), source (MANUAL|AI),
  current_version (UUID|null), created_by, approval_route (UUID|null)}`; JDVersion
  `{version_number, body:{summary, responsibilities[], must_haves[], nice_to_haves[]},
  confidence_score, citations, is_published}`; JDRequest `{requested_by, title, level,
  notes, status (OPEN|FULFILLED|DECLINED)}`.
- **Actions → transition** (see §3): Create → DRAFT; Save draft; Submit → PENDING;
  Approve → PUBLISHED (or → IN_REVIEW if a route is active); **Generate (AI)** → writes
  body + locks PENDING (premium `jd_generator`; **503** if AI unconfigured; 403 if not
  entitled); Revise published → new DRAFT version (published stays live + frozen);
  Archive.
- **States:** library list **(PAGINATED)** · editor (working version) · version history
  (`current_version` = the immutable live one) · generate → 503 / 422 `INVALID_JD_INPUT`
  / 403-locked · requests list **(PAGINATED)**. Validation: title + level + body
  required to submit.

### 2.8 Org Chart — Tree · Person Card · Vacancies · Reassign · Positions
- **Purpose:** browse the reporting tree, view people, manage vacancies, move people.
- **Data:** tree `{nodes:{<id>:{id,email,display,role,headcount,vacancies}}, edges[],
  roots[]}`; person card `{id, email, display_name, display, role, title, manager:{id,
  email, display}|null, direct_reports, filled_positions[], published_jds[]}`; Position
  `{id, title, reports_to, department, status (OPEN|FILLED|CLOSED), filled_by,
  published_jd, opened_at, filled_at}`.
- **Actions → change:** Create position (OPEN); Fill → FILLED (409 if already filled);
  Close → CLOSED; Link/unlink a PUBLISHED JD; **Reassign** a person's manager
  (cycle-checked → **422 REPORTING_CYCLE**).
- **States:** scoped tree (Manager = subtree, HRBP/Admin = whole tenant, multiple
  `roots`) · person card 404 (out of scope) · search results **(PAGINATED)** ·
  vacancies list (array) · positions list **(PAGINATED)** · 409 illegal position
  transition.

### 2.9 Succession — Dashboard · 9-box · Bench · Plan Review  *(MANAGEMENT-ONLY)*
- **Purpose:** critical-role coverage, talent grid, successor bench, succession plans.
- **Data:** dashboard `{critical_roles:[{id,name,criticality,knowledge_risk,status,
  coverage_status,published_plan}]}`; CriticalRole `{name, position, incumbent,
  criticality (HIGH|CRITICAL), knowledge_risk (LOW|MEDIUM|HIGH), risk_notes, status
  (ACTIVE|ARCHIVED)}`; BenchCandidate `{candidate, readiness (READY_NOW|READY_SOON|
  DEVELOPING|NOT_READY), readiness_overridden, notes}`; NineBoxPlacement `{employee,
  cycle, performance_band (LOW|MEDIUM|HIGH derived), potential_band (same, human-set),
  box (1–9)}`; SuccessionPlan `{status (DRAFT|PENDING_HUMAN_REVIEW|PUBLISHED),
  ranked_bench, coverage_status (RED|AMBER|GREEN), red_flags, action_items, source
  (DETERMINISTIC|AI), confidence_score}`.
- **Actions → transition** (see §3): Mark critical role; Add bench; Set readiness
  (override sticks); Assess 9-box (set potential band); Generate analysis → plan
  PENDING_HUMAN_REVIEW; Add action item (PENDING only); **Publish** → PUBLISHED
  (409 from any other state); Enrich (Agent 4) → a NEW `source=AI` plan PENDING
  (deterministic one untouched) or **503**.
- **States:** dashboard (coverage **RED/AMBER/GREEN** chips per role) · **9-box grid**
  (3×3, box 1–9) · bench list **(PAGINATED)** · critical-roles list **(PAGINATED)** ·
  nine-box list **(PAGINATED)** · plan review (PENDING → action-items + Publish; show
  `red_flags` incl. INADEQUATE_COVERAGE on RED) · Manager sees own tier only · Manager
  w/o HRBP cap → 403 on mark/generate/publish.

### 2.10 Analytics — Individual · Department · Calibration Grid
- **Purpose:** performance trends + cohort rollups + the 9-box calibration grid.
- **Data:** individual `{employee, trend:[{cycle, t_score, risk_status, raw_score,
  pace_behind}]}`; department `{head, cycle, cohort_size, min_cohort:5, suppressed
  (bool), aggregate:{headcount, scored, mean_t_score, median_t_score, risk_distribution:
  {ON_TRACK, AT_RISK, CRITICAL}}, individuals:[]}`; calibration `{cycle, total,
  grid:{"1":n,…,"9":n}, placements:[{employee, box, performance_band, potential_band}]}`.
- **States:** individual trend (any role, own; Manager+ for reports) · **department <5
  members → `suppressed:true`, render AGGREGATE ONLY + a "cohort too small (<5)" marker;
  NEVER show individuals** · ≥5 → individuals shown · Employee on /department → 403
  (n/a here) · **calibration = HRBP/Admin ONLY** (Manager → 403). `cycle` is required
  (else 400).

### 2.11 Audit Console  *(MANAGEMENT-ONLY · READ-ONLY · HRBP + Admin)*
- **Purpose:** searchable, immutable activity log.
- **Data (AuditLog):** `{id, actor, action ("review.approved"…), target_type,
  target_id, justification, metadata (JSON), created_at}`. Response is **PAGINATED**.
- **Actions:** filter by actor / action / target_type / target_id / date range;
  paginate. **NO create/edit/delete controls anywhere** (the log is immutable).
- **States:** empty · filtered results · paginated · 403 (non-HRBP/Admin).

### 2.12 Integrations Config  *(ADMIN only)*
- **Purpose:** configure Jira + Slack per tenant.
- **Data (TenantIntegration):** `{kind (JIRA|SLACK), enabled (bool), config (non-secret
  JSON: base_url/email/project/channel/value_field…), secret_ref (the NAME of an env
  var — **NEVER a token value**, never returned)}`.
- **Actions:** Enable/disable; edit non-secret config; set `secret_ref`. The form
  captures a **secret-NAME**, not a secret. Show "token managed out-of-band — enter the
  env-var name, not the secret."
- **States:** list (array) · not-configured (a kind returns 404) · configured/enabled/
  disabled · 400 unknown kind · 403 (non-Admin).

### 2.13 AI Chat Panel + KPI-Nudges Tile
- **Chat (all roles, `chat` feature):** a slide-over/panel. `POST {query}` → response
  `{status, intent, answer, data?}`. States: answer (read-only) · **blocked** (write
  intent → "I can't make changes") · **503** ("Chat not available yet") · **429**
  (budget, show cooldown) · empty query → 400. Read-only assistant; never offers a
  "do it for me" write.
- **KPI-Nudges tile (Manager+):** a list of `{employee, level (CRITICAL|STANDARD|
  SUPPRESSED), message}`. Render CRITICAL prominently; SUPPRESSED as a muted "flag for
  review"; empty = "no nudges". (Plain array, not paginated.)

---

## 3 · State machines (for stepper / timeline UIs)

Render these as steppers/timelines and only enable the transitions valid from the
current state. After any action, re-derive available actions from the returned status
(a stale action → 409).

**Review** — states: `DRAFT · AI_DRAFTING · PENDING_HUMAN_REVIEW · EDITING · APPROVED ·
REJECTED · FINALIZED`. Transitions: request-ai-draft `DRAFT→AI_DRAFTING`; (system)
`AI_DRAFTING→PENDING_HUMAN_REVIEW`; start-edit `{DRAFT,PENDING_HUMAN_REVIEW,REJECTED}
→EDITING`; submit `EDITING→PENDING_HUMAN_REVIEW`; **approve** `PENDING_HUMAN_REVIEW→
APPROVED`; **reject(reason)** `PENDING_HUMAN_REVIEW→REJECTED`; finalize `APPROVED→
FINALIZED` (or enters an approval route). (Surfaced via the approval route tracker +
review detail; PENDING_HUMAN_REVIEW shows the HITL approve/reject/edit affordances.)

**Approval Route** — route status: `IN_PROGRESS → APPROVED | REJECTED | ESCALATED`.
Step status: `PENDING → APPROVED | REJECTED | ESCALATED | SKIPPED`. SEQUENTIAL: the
active step = the lowest-order PENDING; approve activates the next; last approve →
route APPROVED. PARALLEL: all steps PENDING at once; route APPROVED when all REQUIRED
steps approve; any REQUIRED reject → route REJECTED. Overdue PENDING → escalated.

**JD Lifecycle** — `DRAFT · PENDING_HUMAN_REVIEW · IN_REVIEW · PUBLISHED · ARCHIVED`.
submit `DRAFT→PENDING_HUMAN_REVIEW`; generate(AI) → PENDING (source=AI); approve
`PENDING→PUBLISHED` or `→IN_REVIEW` (if a route is active); route complete `IN_REVIEW→
PUBLISHED`; route rejected `IN_REVIEW→PENDING_HUMAN_REVIEW`; revise `PUBLISHED→DRAFT`
(new version; old stays live + frozen); archive → ARCHIVED.

**Succession Plan** — `DRAFT · PENDING_HUMAN_REVIEW · PUBLISHED`. generate →
PENDING_HUMAN_REVIEW (source=DETERMINISTIC); add action-item (PENDING only); **publish**
`PENDING_HUMAN_REVIEW→PUBLISHED` (409 from elsewhere); enrich(Agent 4) → a NEW
`source=AI` plan PENDING (the deterministic one is untouched).

---

## 4 · Cross-cutting UX rules (repeat for v0's emphasis)
1. **HITL:** drafts (`PENDING_HUMAN_REVIEW`, AI sources) are never final — always show
   Approve / Reject(reason) / Edit + a "Draft — pending review" badge + confidence
   (warn if < 0.70).
2. **Feature-flag locking:** locked premium = disabled + "Upgrade to unlock", never an
   error, never silently hidden.
3. **404 = "not yours / not there":** on a detail/action 404, route back to the list;
   never imply the record exists elsewhere.
4. **429:** honour `Retry-After` (a cooldown timer); show the `upgrade_hint` CTA if
   present.
5. **Management-only invisibility:** Succession, Department/Calibration analytics, and
   the Audit console are hidden from anyone outside the noted roles.
6. **Pagination:** the lists marked **(PAGINATED)** use the envelope
   `{count, next, previous, results}` — build a reusable paginated-table component
   (page + page_size, default 50). All other lists are plain arrays.

---

## 5 · Mock data (use these exact shapes; UUIDs/timestamps are placeholders)

```jsonc
// session: GET /api/auth/me
{ "id":"u-admin-001","email":"admin@acme.test","display_name":null,"display":"admin@acme.test",
  "role":"ADMIN","tenant_id":"t-acme","mfa_enabled":false,"manager_id":null }

// Admin · Users (PLAIN ARRAY)
[
 {"id":"u-1","email":"ada@acme.test","display_name":"Ada Lovelace","display":"Ada Lovelace","role":"MANAGER","manager":"u-hrbp","is_active":true,"mfa_enabled":true},
 {"id":"u-2","email":"reza@acme.test","display_name":null,"display":"reza@acme.test","role":"EMPLOYEE","manager":"u-1","is_active":true,"mfa_enabled":false},
 {"id":"u-3","email":"old@acme.test","display_name":"Former Person","display":"Former Person","role":"EMPLOYEE","manager":"u-1","is_active":false,"mfa_enabled":false}
]

// Tenant config: GET /api/admin/tenant-config
{ "id":"cfg-1","settings":{"locale":"en-GB","weekStart":"MON","fiscalYearStart":"04-01"} }

// Entitlement: GET /api/billing/entitlement
{ "seat_count":25,"feature_packs":["STARTER"],"unlocked_agents":["agent2"],"tier_label":"Starter" }

// Feature flags: GET /api/billing/feature-flags  (and /my-features, same shape)
{ "agent1":false,"agent2":true,"agent3":false,"agent4":false,"agent5":false,
  "chat":true,"jd_generator":false,"career_roadmap":false }

// Upgrade prompt: GET /api/billing/upgrade-prompt
{ "current_packs":["STARTER"],"tier_label":"Starter",
  "feature_flags":{"agent1":false,"agent2":true,"agent3":false,"agent4":false,"agent5":false,"chat":true,"jd_generator":false,"career_roadmap":false},
  "locked_features":["agent1","agent3","agent4","agent5","jd_generator","career_roadmap"],
  "upgrade":{"pack":"FULL_AI","would_unlock":["agent1","agent3","agent4","agent5","jd_generator","career_roadmap"],
             "note":"Conceptual only — no pricing or payment is captured."} }

// Approvals · workflows (PLAIN ARRAY)
[ {"id":"wf-1","name":"Review sign-off","artifact_type":"review","mode":"SEQUENTIAL","active":true,
   "steps":[{"order":1,"approver_kind":"ROLE","approver_role":"MANAGER","required":true,"timeout_hours":48},
            {"order":2,"approver_kind":"ROLE","approver_role":"HRBP","required":true,"timeout_hours":48}]} ]

// Approvals · inbox (PLAIN ARRAY — SEQUENTIAL shows only the active step)
[ {"id":"si-9","route":"rt-7","order":2,"approver_role":"HRBP","status":"PENDING","due_at":"2026-06-20T17:00:00Z","artifact_type":"review","artifact_id":"rv-3"} ]

// Approvals · route tracker: GET /api/approvals/routes/<id>  (OBJECT)
{ "id":"rt-7","status":"IN_PROGRESS","mode":"SEQUENTIAL","artifact_type":"review","artifact_id":"rv-3","initiated_by":"u-1",
  "step_instances":[
    {"order":1,"approver":"u-1","approver_role":"MANAGER","status":"APPROVED","decided_by":"u-1","decided_at":"2026-06-12T10:00:00Z","comment":"LGTM","escalated":false,"due_at":null},
    {"order":2,"approver":null,"approver_role":"HRBP","status":"PENDING","decided_by":null,"decided_at":null,"comment":"","escalated":false,"due_at":"2026-06-20T17:00:00Z"}
  ] }

// JD library: GET /api/jd/  (PAGINATED)
{ "count":2,"next":null,"previous":null,"results":[
   {"id":"jd-1","title":"Staff Engineer","level":"L5","department":"Engineering","status":"PUBLISHED","source":"MANUAL","current_version":"jdv-1","approval_route":null},
   {"id":"jd-2","title":"Analytics Engineer","level":"L4","department":"Data","status":"PENDING_HUMAN_REVIEW","source":"AI","current_version":null,"approval_route":null}
 ] }
// JDVersion (version history; sub-list — array): GET /api/jd/<id>/versions
[ {"version_number":2,"is_published":true,"confidence_score":null,"citations":null,
   "body":{"summary":"Owns platform reliability.","responsibilities":["Lead architecture","Mentor"],"must_haves":["8+ yrs"],"nice_to_haves":["Go"]}},
  {"version_number":1,"is_published":false,"confidence_score":"0.8200","citations":[{"type":"inputs_snapshot"}],
   "body":{"summary":"Draft.","responsibilities":["Ship"],"must_haves":["5+ yrs"],"nice_to_haves":[]}} ]
// JD requests: GET /api/jd/requests  (PAGINATED)
{ "count":1,"next":null,"previous":null,"results":[ {"id":"jr-1","requested_by":"u-1","title":"SRE","level":"L4","notes":"urgent","status":"OPEN"} ] }

// Org tree: GET /api/org/tree  (OBJECT)
{ "roots":["u-hrbp"],
  "nodes":{ "u-hrbp":{"id":"u-hrbp","email":"hrbp@acme.test","display":"Priya HR","role":"HRBP","headcount":4,"vacancies":1},
            "u-1":{"id":"u-1","email":"ada@acme.test","display":"Ada Lovelace","role":"MANAGER","headcount":2,"vacancies":1},
            "u-2":{"id":"u-2","email":"reza@acme.test","display":"reza@acme.test","role":"EMPLOYEE","headcount":1,"vacancies":0} },
  "edges":[["u-hrbp","u-1"],["u-1","u-2"]] }
// Person card: GET /api/org/people/<id>  (OBJECT)
{ "id":"u-1","email":"ada@acme.test","display_name":"Ada Lovelace","display":"Ada Lovelace","role":"MANAGER",
  "title":"Engineering Manager","manager":{"id":"u-hrbp","email":"hrbp@acme.test","display":"Priya HR"},
  "direct_reports":2,"filled_positions":[{"id":"p-1","title":"Engineering Manager","department":"Engineering","published_jd":"jd-1"}],"published_jds":["jd-1"] }
// Org search: GET /api/org/search?q=  (PAGINATED)
{ "count":1,"next":null,"previous":null,"results":[ {"id":"u-1","email":"ada@acme.test","display_name":"Ada Lovelace","display":"Ada Lovelace","role":"MANAGER","title":"Engineering Manager"} ] }
// Vacancies: GET /api/org/vacancies (ARRAY) ; Positions: GET /api/org/positions (PAGINATED)
{ "count":1,"next":null,"previous":null,"results":[ {"id":"p-2","title":"SRE","reports_to":"u-1","department":"Engineering","status":"OPEN","filled_by":null,"published_jd":"jd-1","opened_at":"2026-06-01T09:00:00Z","filled_at":null} ] }

// Succession dashboard: GET /api/succession/dashboard  (OBJECT)
{ "critical_roles":[
   {"id":"cr-1","name":"Head of Platform","criticality":"CRITICAL","knowledge_risk":"HIGH","status":"ACTIVE","coverage_status":"GREEN","published_plan":"sp-1"},
   {"id":"cr-2","name":"Lead DBA","criticality":"HIGH","knowledge_risk":"MEDIUM","status":"ACTIVE","coverage_status":"RED","published_plan":null} ] }
// Bench: GET /api/succession/critical-roles/<id>/bench  (PAGINATED)
{ "count":2,"next":null,"previous":null,"results":[
   {"id":"bc-1","candidate":"u-1","readiness":"READY_NOW","readiness_overridden":false,"notes":"strong"},
   {"id":"bc-2","candidate":"u-2","readiness":"DEVELOPING","readiness_overridden":true,"notes":""} ] }
// Nine-box: GET /api/succession/nine-box  (PAGINATED)
{ "count":2,"next":null,"previous":null,"results":[
   {"id":"nb-1","employee":"u-1","cycle":"cy-1","performance_band":"HIGH","potential_band":"HIGH","box":9},
   {"id":"nb-2","employee":"u-2","cycle":"cy-1","performance_band":"MEDIUM","potential_band":"MEDIUM","box":5} ] }
// Plan: GET /api/succession/plans/<id>  (OBJECT)
{ "id":"sp-1","status":"PENDING_HUMAN_REVIEW","coverage_status":"GREEN","source":"DETERMINISTIC","confidence_score":null,
  "ranked_bench":[{"candidate":"u-1","readiness":"READY_NOW"},{"candidate":"u-2","readiness":"DEVELOPING"}],
  "red_flags":[],"action_items":[{"text":"Pair with incumbent for one quarter","added_by":"u-hrbp"}] }

// Analytics · individual: GET /api/analytics/individual  (OBJECT)
{ "employee":"u-2","trend":[
   {"cycle":"cy-1","t_score":"55.0000","risk_status":"ON_TRACK","raw_score":"0.7200","pace_behind":false},
   {"cycle":"cy-0","t_score":"42.0000","risk_status":"AT_RISK","raw_score":"0.5500","pace_behind":true} ] }
// Analytics · department — SUPPRESSED (<5)  (OBJECT)
{ "head":"u-1","cycle":"cy-1","cohort_size":3,"min_cohort":5,"suppressed":true,
  "aggregate":{"headcount":3,"scored":3,"mean_t_score":49.5,"median_t_score":50.0,"risk_distribution":{"ON_TRACK":1,"AT_RISK":2,"CRITICAL":0}},
  "individuals":[], "note":"Cohort too small (<5); individual values suppressed." }
// Analytics · department — FULL (>=5): same shape with "suppressed":false and individuals:[{"employee","t_score","risk_status"},…]
// Analytics · calibration: GET /api/analytics/calibration?cycle=  (OBJECT, HRBP/Admin)
{ "cycle":"cy-1","total":2,"grid":{"1":0,"2":0,"3":0,"4":0,"5":1,"6":0,"7":0,"8":0,"9":1},
  "placements":[{"employee":"u-1","box":9,"performance_band":"HIGH","potential_band":"HIGH"},{"employee":"u-2","box":5,"performance_band":"MEDIUM","potential_band":"MEDIUM"}] }

// Audit console: GET /api/audit/logs  (PAGINATED)
{ "count":127,"next":"/api/audit/logs?page=2","previous":null,"results":[
   {"id":"al-1","actor":"u-hrbp","action":"succession_plan.published","target_type":"succession_plan","target_id":"sp-1","justification":"","metadata":{"coverage_status":"GREEN"},"created_at":"2026-06-13T14:05:00Z"},
   {"id":"al-2","actor":"u-1","action":"review.approved","target_type":"review","target_id":"rv-3","justification":"","metadata":{},"created_at":"2026-06-12T10:00:00Z"} ] }

// Integrations: GET /api/integrations/  (ARRAY) ; GET /api/integrations/<kind>  (OBJECT, 404 if not configured)
[ {"id":"int-1","kind":"SLACK","enabled":true,"config":{"channel":"#perf"},"secret_ref":"SLACK_WEBHOOK_ACME"},
  {"id":"int-2","kind":"JIRA","enabled":false,"config":{"base_url":"https://acme.atlassian.net","email":"bot@acme.test","value_field":"customfield_actual"},"secret_ref":"JIRA_TOKEN_ACME"} ]

// AI chat: POST /api/ai/chat {query}  →  (OBJECT)
{ "status":"ok","intent":"read","answer":"ada@acme.test has 3 goal(s).","data":["Ship platform v2","Mentor 2 engineers","Cut p95 latency"] }
// blocked write intent:
{ "status":"blocked","intent":"write","answer":"I'm a read-only assistant — I can't make changes or approvals." }

// KPI nudges: GET /api/ai/nudges  (ARRAY, Manager+)
[ {"employee":"u-2","level":"CRITICAL","message":"Performance is critical — immediate attention needed."},
  {"employee":"u-1","level":"STANDARD","message":"At risk — a check-in is recommended."} ]

// Example ERROR body (422 domain validation) — render `detail`, key off `code`:
{ "detail":"Cannot publish a succession plan in status PUBLISHED.","code":"ILLEGAL_PLAN_TRANSITION" }
```

---

## 6 · WIRING NOTES — for later (NOT for v0)
> Ignore this section when generating; it maps each mock to the real endpoint so the
> downloaded UI can be connected to the live API afterward. `method · path ·
> capability`. Auth: `Authorization: Bearer <jwt>` on all; tenant is implicit.

| Screen | Real endpoint(s) | Capability |
|---|---|---|
| Auth/MFA | `POST /api/auth/login` · `/mfa/challenge` · `/mfa/enroll(+/confirm)` · `/token/refresh` · `/logout` · `GET /api/auth/me` | authenticated |
| Dashboard | compose: `GET /api/auth/me`, `GET /api/approvals/inbox`, `GET /api/ai/nudges`, `GET /api/billing/my-features` | per-tile |
| Admin Users | `GET,POST /api/admin/users` · `POST /api/admin/users/<id>/role\|deactivate\|reactivate\|reporting-line\|display-name` | `manage_users_roles` (Admin) |
| Tenant Config | `GET,PUT /api/admin/tenant-config` | `manage_tenant_config` (Admin) |
| Entitlements/Billing | `GET /api/billing/entitlement` · `POST /api/billing/upgrade` · `PATCH /api/billing/seats` · `GET /api/billing/feature-flags` · `GET /api/billing/upgrade-prompt` | `manage_tenant` / `manage_entitlements` (Admin) |
| Feature flags (any UI) | `GET /api/billing/my-features` | authenticated (own tenant) |
| Approvals inbox/tracker | `GET /api/approvals/inbox` · `GET /api/approvals/routes/<id>` · `GET /api/approvals/routes?artifact_type=&artifact_id=` · `POST /api/approvals/steps/<id>/approve\|reject` | `act_on_approval_step` (Manager+) |
| Approval designer | `GET,POST /api/approvals/workflows` · `…/<id>/activate\|deactivate` | `configure_approval_workflow` (HRBP/Admin) |
| JD library/editor | `GET,POST /api/jd/` · `GET /api/jd/<id>` · `…/versions` · `…/export` · `…/save-draft\|submit\|approve\|revise\|archive` · `…/generate` · `GET,POST /api/jd/requests` · `…/requests/<id>/fulfil\|decline` | `view_jd_library` / `manage_jd_library` / `generate_jd` |
| Org chart | `GET /api/org/tree` · `/people/<id>` · `/search?q=` · `/vacancies` · `/export` · `GET,POST /api/org/positions` · `…/positions/<id>/fill\|close\|link-jd\|unlink-jd` · `POST /api/org/reassign` | `view_org_chart` / `manage_positions` / `reassign_reporting_line` |
| Succession | `GET /api/succession/dashboard` · `…/critical-roles(+CRUD,/knowledge-risk,/archive,/bench,/generate)` · `…/bench/<id>/readiness` · `…/nine-box` · `…/plans/<id>(+/action-item,/publish,/enrich)` | `view_succession` / `manage_critical_roles` / `manage_bench` / `assess_nine_box` / `generate_succession_analysis` / `publish_succession_plan` |
| Analytics | `GET /api/analytics/individual[?employee=]` · `/department?head=&cycle=` · `/calibration?cycle=` · `/export?…` | `view_individual_analytics` / `view_department_analytics` / `view_calibration_grid` |
| Audit console | `GET /api/audit/logs?actor=&action=&target_type=&target_id=&date_from=&date_to=&page=&page_size=` | `view_audit_console` (HRBP/Admin) |
| Integrations | `GET /api/integrations/` · `GET,PUT /api/integrations/<kind>` | `manage_integrations` (Admin) |
| AI Chat | `POST /api/ai/chat {query}` | `use_chat` + `requires_entitlement("chat")` |
| KPI nudges tile | `GET /api/ai/nudges` | `view_team_scores` (Manager+) |

Paginated lists (`{count,next,previous,results}`, `?page=&page_size=` ≤200): JD list +
requests, org search + positions, succession bench + critical-roles + nine-box, audit
logs. All other lists are plain arrays. (The Review state machine is surfaced via the
approval route tracker; a dedicated Reviews-management screen + the mobile-web
self-service surface are later builds.)
