# Frontend Contract — 02 · State Machines

The lifecycles the UI must **visualise** (steppers / timelines / status badges) and
**drive** (which actions are offered from which state, and who may take them).
Derived from the actual transition tables (`apps/reviews/state_machine.py`, the
`apps/approvals` engine, the JD lifecycle, the succession plan service, the career
service). The backend is the authority — always re-derive available actions from the
entity's current status after each action (a stale action → **409**).

Status-badge convention: terminal/positive = APPROVED/PUBLISHED/FINALIZED/RELEASED;
in-flight = PENDING_*/IN_PROGRESS/AI_DRAFTING/EDITING; negative = REJECTED;
neutral = DRAFT/ARCHIVED.

---

## 1. Review (Module 3) — `Review.state`

**States:** DRAFT · AI_DRAFTING · PENDING_HUMAN_REVIEW · EDITING · APPROVED ·
REJECTED · FINALIZED.

| From | Action (endpoint) | → To | Who can (capability) |
|---|---|---|---|
| DRAFT | request-ai-draft | AI_DRAFTING | Manager+ (`run_ai_review_draft`) — Agent 1, needs `agent1` feature (FULL_AI) |
| DRAFT / PENDING_HUMAN_REVIEW / REJECTED | start-edit | EDITING | Manager+ (`manage_reviews`) |
| AI_DRAFTING | (system) ai_draft_ready | PENDING_HUMAN_REVIEW | system (locks the AI draft) |
| EDITING | submit (save-draft alias) | PENDING_HUMAN_REVIEW | Manager+ (`manage_reviews`) |
| PENDING_HUMAN_REVIEW | **approve** | APPROVED | Manager+ (`approve_review`) — sets `human_reviewer` |
| PENDING_HUMAN_REVIEW | **reject** (reason required) | REJECTED | Manager+ (`approve_review`) |
| APPROVED | finalize | FINALIZED | Manager+ (`finalize_review`) — **single-step UNLESS an "review" approval route is active, then it enters the route (stays APPROVED + links `approval_route`)** |
| APPROVED | (route rejected → callback) | EDITING | system (an approval route rejection returns it to the author) |

**UI notes:** AI_DRAFTING is transient (poll/spinner). PENDING_HUMAN_REVIEW is the
HITL gate — render Approve / Reject(reason) / Edit + the draft badge + confidence +
low-confidence warning. FINALIZED is read-only (the employee can read their own).
Re-running a terminal/illegal action (approve twice, edit a FINALIZED review) → 409.
DB-level guarantee: a FINALIZED review always has a `human_reviewer`.

---

## 2. Approval Route (Module 5) — `ApprovalRoute.status` + `ApprovalStepInstance.status`

**Route status:** IN_PROGRESS · APPROVED · REJECTED · ESCALATED (reserved — only a
dead-end with no escalation target; rare). **Step status:** PENDING · APPROVED ·
REJECTED · ESCALATED · SKIPPED.

**Mode = SEQUENTIAL:** the ACTIVE step is the lowest-order PENDING one (computed) —
the inbox shows only it; other steps wait. **Mode = PARALLEL:** all steps are PENDING
at once; the route completes when every REQUIRED step is approved.

| From (step) | Action (endpoint) | Effect |
|---|---|---|
| PENDING (active) | `steps/<id>/approve` | step → APPROVED. SEQUENTIAL: activates the next step; if last → route APPROVED. PARALLEL: route APPROVED when all required approved. |
| PENDING | `steps/<id>/reject` | step → REJECTED → **route REJECTED** (ends it). |
| PENDING (overdue) | (beat) escalate | step reassigned to its escalation target (`escalated=true`, new due_at). |

Route completion fires the artifact's callback (review → FINALIZED; JD → PUBLISHED).
Decisions are restricted to the assigned approver / in-scope role-slot holder
(engine-enforced → 403); out-of-order or already-decided → 409.

**UI notes:** render the route as a stepper (per-step approver, status, due_at,
escalated badge). For SEQUENTIAL, only the active step is actionable in the inbox.

---

## 3. JD Lifecycle (Module 6) — `JobDescription.status`

**States:** DRAFT · PENDING_HUMAN_REVIEW · IN_REVIEW (in an approval route) ·
PUBLISHED · ARCHIVED. `current_version` = the live PUBLISHED version (immutable);
the "working version" is the latest `JDVersion`.

| From | Action (endpoint) | → To | Who |
|---|---|---|---|
| (none) | create | DRAFT (+ v1) | HRBP+ (`manage_jd_library`) |
| DRAFT / PENDING | save-draft | (same) | HRBP+ |
| DRAFT | generate (AI) | PENDING_HUMAN_REVIEW (source=AI) | HRBP+ (`generate_jd`, `jd_generator` feature = FULL_AI) |
| DRAFT | submit | PENDING_HUMAN_REVIEW | HRBP+ (validates inputs → 422) |
| PENDING_HUMAN_REVIEW | approve | **PUBLISHED** (single-step) OR **IN_REVIEW** (enters an active "jd" route) | HRBP+ |
| IN_REVIEW | (route complete) | PUBLISHED | system |
| IN_REVIEW | (route rejected) | PENDING_HUMAN_REVIEW | system |
| PUBLISHED | revise | DRAFT (new version; published stays live + frozen) | HRBP+ |
| any | archive | ARCHIVED | HRBP+ |

**UI notes:** version history shows all `JDVersion`s; only `current_version` is the
live published one. Revising a published JD opens a new draft while the published
version stays readable. Illegal transition → 409 ILLEGAL_JD_TRANSITION.

---

## 4. Succession Plan (Module 8) — `SuccessionPlan.status` (management-only)

**States:** DRAFT · PENDING_HUMAN_REVIEW · PUBLISHED. (The deterministic flow goes
straight to PENDING_HUMAN_REVIEW.)

| From | Action (endpoint) | → To | Who |
|---|---|---|---|
| (none) | generate (deterministic) | PENDING_HUMAN_REVIEW (source=DETERMINISTIC) | HRBP+ (`generate_succession_analysis`) |
| PENDING_HUMAN_REVIEW | add action-item | (same) | HRBP+ (`publish_succession_plan`) |
| PENDING_HUMAN_REVIEW | **publish** | PUBLISHED (→ appears on dashboard) | HRBP+ |
| (any plan) | enrich (Agent 4) | **a NEW source=AI plan PENDING_HUMAN_REVIEW** (deterministic plan untouched) OR 503 | HRBP+ |

**UI notes:** publish only from PENDING (else 409 ILLEGAL_PLAN_TRANSITION); add an
action item only while PENDING. The enrich action creates a *separate* AI plan for
re-review — never overwrites the deterministic one. Coverage badge RED/AMBER/GREEN;
RED carries an INADEQUATE_COVERAGE red flag.

---

## 5. Career Roadmap (Module 9) — `DevelopmentRoadmap.status` + `RoadmapProgress.status`

**Roadmap states:** DRAFT · ACTIVE · ARCHIVED. `advisory` is **always true** (a DB
CHECK enforces it — the UI must always present a roadmap as advice, never an
instruction/promotion).

| From | Action (endpoint) | → To | Who |
|---|---|---|---|
| (none) | select target (`POST /target`) | ACTIVE (source=DETERMINISTIC) | self / Manager+ for reports |
| ACTIVE | regenerate | ACTIVE (refreshed tiers) | self / Manager+ |
| (any) | enrich (Agent) | **a NEW source=AI roadmap DRAFT** (human accepts → ACTIVE) OR 503 | self / Manager+ (`career_roadmap` feature = FULL_AI) |

**Per-tier progress** (`RoadmapProgress.status`): NOT_STARTED → IN_PROGRESS → DONE
(`POST /roadmaps/<id>/progress` `{tier_index, status}`; any transition allowed; one
row per tier). UI: render tiers as a checklist with a per-tier status control.

**UI notes:** an AI-enriched roadmap arrives as a DRAFT for human acceptance (don't
auto-activate). The roadmap NEVER carries succession data — only the performance
band + weak categories + tiers.
