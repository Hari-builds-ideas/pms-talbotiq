# User Workflows — Talbotiq PMS

> **Purpose.** Every major end-to-end workflow: goal · trigger · actor · step-by-step
> (with state transitions + 🔒HITL gates) · success state · failure/recovery states
> (by error code) · concrete **UX improvement opportunities**. **Grounding.**
> `docs/frontend-contract/04_role_journeys.md` + `02_state_machines.md` + the real
> screens. 🔒 = a human gate the UI must surface (never auto-advance). The improvement
> notes feed `ux-spec.md` (Phase 8).

---

## W1. Run a performance review (with AI draft) — the flagship HITL flow
- **Goal:** produce a fair, finalized review for a report.
- **Actor / trigger:** Manager+, in an ACTIVE cycle; opens Reviews.
- **Steps:**
  1. Reviews list (team-scoped, cycle filter) → open or **New review** `{employee, cycle}` (needs ACTIVE cycle) → `DRAFT`.
  2. Either **Request AI draft** (`DRAFT→AI_DRAFTING`, Agent 1; needs `agent1` FULL_AI) → system → **`PENDING_HUMAN_REVIEW`** with draft_body + confidence + citations; **or** Start-edit → write → Submit (`EDITING→PENDING`).
  3. 🔒 **Approve** (`→APPROVED`, sets `human_reviewer`) or **Reject(reason)** (`→REJECTED`). The UI shows the draft badge + confidence + low-confidence (<0.70) warning — never "final".
  4. **Finalize** (`APPROVED→FINALIZED`) — *or*, if a "review" approval route is active, it enters the route (a stepper appears; the route callback finalizes).
- **Success:** `FINALIZED` (read-only; the employee can read their own); a complete timeline.
- **Failure/recovery:** 503 (Agent 1 not configured) → "AI not available", manual path still works · 403 (no FULL_AI) → locked + upgrade · 409 (e.g. approve twice) → re-fetch + re-derive actions · 422 `REJECTION_REASON_REQUIRED` / `HITL_APPROVAL_REQUIRED` → inline.
- **UX opportunities:** AI draft is async/opaque ("page updates automatically") → **stream the draft or show a real "generating…" state + optimistic poll**; evidence panel is badge-dense → **target-vs-actual viz**; assessments cramped → clearer SELF/MANAGER grouping + timestamps; **bulk "review all reports this cycle"**; **draft-vs-final / self-vs-manager side-by-side**; comment threads; canned reject reasons.

## W2. Run a goal/KPI cycle
- **Goal:** set weighted goals + KPIs, capture actuals, score, approve.
- **Actor / trigger:** HRBP/Admin opens/advances a `PerformanceCycle`; Manager sets reports' goals; employees record their own actuals.
- **Steps:**
  1. (HRBP/Admin) ensure an ACTIVE cycle.
  2. (Manager) **New goal** `{employee, cycle, title, weight, kpis[]}` — **KPI weights = 100** and **active-goal weights = 100** (live running-sum).
  3. (Employee, own) **Record actual** on a KPI (`POST actuals`; own-only → a peer's 404).
  4. (Manager) **Approve** a goal; **Recompute** scores → CycleScore (t_score, risk, pace) updates.
- **Success:** active goals summing to 100, scored, risk badges live.
- **Failure/recovery:** 422 weight-sum (99.99/100.01) → the running-sum indicator + the exact message · 422 `target_value>0` · 404 recording a peer's actual.
- **UX opportunities:** create dialog is a form-dump → **a guided wizard with a live weight bar**; actuals one-by-one → **batch entry for a team + unit context**; recompute opaque → **show what changed**; **progress-to-target gauges**; goal→review linkage.

## W3. Approvals routing (design → route → act → track)
- **Goal:** route a review/JD through human approval with escalation.
- **Actor / trigger:** Admin/HRBP designs a workflow; finalizing a review / approving a JD with an active route triggers a route; approvers act.
- **Steps:**
  1. (Admin/HRBP) **Workflow designer** → define SEQUENTIAL/PARALLEL steps (ROLE/NAMED, timeouts, escalation) → **Activate** (≤1 active per artifact_type). *(Edit = re-create; in-flight routes are snapshotted.)*
  2. An artifact action that has an active route creates an `ApprovalRoute` (IN_PROGRESS).
  3. (Approver) **Inbox** shows assigned steps (SEQUENTIAL = only the active step) → **Approve/Reject(comment)** → the route advances/ends. Overdue steps escalate (beat).
  4. **Route tracker** stepper shows per-step status/due/escalated. Route completion fires the artifact callback (review→FINALIZED, JD→PUBLISHED).
- **Success:** route APPROVED → artifact published/finalized.
- **Failure/recovery:** 403 (not the assignee) · 409 (out-of-order / already decided) → re-fetch · route REJECTED → returns the artifact to the author (EDITING / PENDING).
- **UX opportunities:** inbox approval opens a sheet → **inline approve**; tracker doesn't highlight "your step" / time-left; designer is a numbered list → **visual routing + conditions**; **email/Slack notification** (approvers only see it on login today); bulk.

## W4. 360° feedback, end to end (request → give → summarize → release → subject view)
- **Goal:** collect anonymised multi-rater feedback and release an AI summary to the subject.
- **Actor / trigger:** Manager/HRBP opens a `FeedbackCycle`.
- **Steps:**
  1. (Manager+) **Create** cycle for a subject → **Open** (`DRAFT→COLLECTING`) → **Invite** givers (relationship per invitation).
  2. (Givers) **Give feedback** (invitation = authz; giver server-set, never egressed); a group counts toward `min_volume` (default 3).
  3. (Manager+) **Close** (`→CLOSED`) → runs **Agent 3** → `FeedbackSummary` PENDING (or **HRBP_HOLD** if a breach/sensitive guard tripped). Sections NULL until Agent 3 ran (never fabricate).
  4. 🔒 (HRBP) **Summaries to release** → read the anonymised payload (no givers) → **Release** (`→RELEASED`).
  5. (Subject) **My 360** → the RELEASED summary (auto-discovered via `/my-cycles`); below-threshold groups marked suppressed.
- **Success:** subject sees the released, anonymised, threshold-gated summary.
- **Failure/recovery:** 503 (Agent 3 not configured) at close → cycle still closes, summary holds · 403 `SUMMARY_NOT_RELEASED` before release · sections NULL = "not generated".
- **UX opportunities:** give dialog lacks who/why context; **response-rate per cycle ("4/5 responded") + reminders**; My-360 PENDING is a dead "not released yet"; release is one-button → **a real HITL review (read sections + confidence + edit-before-release)**; explain confidence.

## W5. Succession: generate → enrich → publish (management-only)
- **Goal:** assess critical-role coverage and publish a succession plan.
- **Actor / trigger:** HRBP/Admin (Manager = own-tier bench/9-box only); opens Succession. **Invisible to employees (404).**
- **Steps:**
  1. (HRBP) Mark **critical roles** + knowledge risk; (Manager+) add **bench** candidates + set **readiness** (override sticks); assess **9-box** (potential human-assigned, performance derived).
  2. (HRBP) **Generate** a plan (deterministic) → `PENDING_HUMAN_REVIEW` (ranked bench, coverage RED/AMBER/GREEN, red flags).
  3. (HRBP) Add **action items** (PENDING only) → 🔒 **Publish** (`→PUBLISHED`, appears on the dashboard).
  4. (Optional) **Enrich** with Agent 4 → a **new** source=AI plan PENDING for re-review (the deterministic plan untouched).
- **Success:** a PUBLISHED plan with coverage status on the dashboard.
- **Failure/recovery:** 409 `ILLEGAL_PLAN_TRANSITION` (publish not from PENDING) · 404 (employee, or Manager out-of-tier) · 503 (Agent 4 not configured) on enrich.
- **UX opportunities:** role cards lack **bench-depth / successor-pool preview**; 9-box cells cap at 5 with **no click-to-drill**; **no plan detail view** (only a published badge); **no "covered in N years?" scenario**; coverage as a heatmap.

## W6. Career roadmap (own / for reports)
- **Goal:** an advisory development path toward a target role.
- **Actor / trigger:** self or Manager+ for a report; opens Career.
- **Steps:**
  1. **Choose target** (a PUBLISHED JD or a Position; exactly one) → deterministic `ACTIVE` roadmap (skill gap + tiers).
  2. **Refresh** (recompute deterministic) and/or **Enrich with AI** (FULL_AI) → a **new** source=AI **DRAFT** roadmap (advisory; ⚠ no "accept→ACTIVE" endpoint — it coexists).
  3. Mark **per-tier progress** (NOT_STARTED↔IN_PROGRESS↔DONE).
- **Success:** an active advisory roadmap with tracked tier progress.
- **Failure/recovery:** 422 `TARGET_AMBIGUOUS` / `TARGET_NOT_PUBLISHED` · 503 (enrich, no agent) · 403/upgrade (no FULL_AI). The roadmap NEVER carries succession data.
- **UX opportunities:** target dialog has no role-requirement preview; **progress-to-target visualization**; tiers are abstract → **learning resources / mentors / next concrete step**; enrich is all-or-nothing → merge/cherry-pick; resolve the DRAFT-vs-ACTIVE AI ambiguity (add an accept endpoint or frame the AI roadmap as an advisory alternative).

## W7. Entitlement upgrade (STARTER → FULL_AI)
- **Goal:** unlock premium AI features tenant-wide.
- **Actor / trigger:** Admin; opens Billing on a STARTER tenant (globex).
- **Steps:** see the feature matrix + locked premium features → open the **upgrade modal** (`upgrade-prompt`: would_unlock list) → **Upgrade to FULL_AI** → every premium flag flips instantly (seats unchanged) → the UI unlocks app-wide.
- **Success:** locked features (Agent 1 draft, JD generate, career enrich, agents 3–5) become live; the premium upsells disappear.
- **Failure/recovery:** 403 (non-admin). Conceptual — no payment capture.
- **UX opportunities:** surface the **AI-usage / TokenLedger cost story** here; per-feature descriptions; seat utilization/forecast; a clearer "what unlocks" before/after.

## W8. Admin setup — users, integrations, audit
- **W8a Users:** create user `{email, role, manager?}` → set role / reporting-line (cycle-checked → 422) / display-name / (de)activate. *Failure:* 422 EMAIL_TAKEN/UNKNOWN_ROLE, 404 cross-tenant. *Improve:* bulk/CSV import, role-capability guidance, onboarding email, a visual reporting chain.
- **W8b Integrations:** enable Jira/Slack → non-secret config + a `secret_ref` env-var **NAME** (never a token) → save. *Improve:* "test connection", help/examples, an event log.
- **W8c Audit:** filter (actor/action/target/date) + paginate; **no mutation** (immutable). *Improve:* date-range filter, humanised actions, links to the target artifact, export.

## W9. AI chat (read-only, RBAC-bound)
- **Goal:** answer a natural-language question within the caller's own scope.
- **Actor / trigger:** any role; Topbar "Ask AI" → the chat sheet.
- **Steps:** type a query → the LLM classifies read-vs-write → a **read** answer is grounded in the caller's scoped data (goals + cycle score/risk); a **write** intent is **blocked** ("I can't make changes"); an out-of-scope target returns nothing.
- **Success:** a grounded, scope-safe answer; never data the caller couldn't reach.
- **Failure/recovery:** 503 (no provider) → "Chat not available yet" · 429 (chat budget) → Retry-After · empty query → 400.
- **UX opportunities:** **stream the answer**; role/data-personalised suggested prompts (only 2 generic ones today); session history; explain *why* a write was blocked and *what data* it can see.

---

## Cross-cutting workflow principles (must hold in any redesign)
- **Every AI/automated artifact passes a human gate** before it's "real": review
  approve→finalize, feedback summary release, succession plan publish, JD approve→publish,
  career roadmap (advisory). Build approve/reject/publish/release as **first-class steps**.
- **Premium prompts, never dead ends:** a FULL_AI-only feature on a STARTER tenant shows
  the locked state + the upgrade path.
- **404 = not yours/not there:** an out-of-scope detail/action routes back to the list.
- **Re-derive actions after every action** (status changed → 409 on a stale action).
- **Surface async work** (AI_DRAFTING, route progress, summary generation) as intentional
  "working…" states with poll/refetch — the system has **no websockets**.
