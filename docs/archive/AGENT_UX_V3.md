# AGENT_UX_V3.md — make the agent FEEL like an agent (experience layer over the existing gate)

**The problem (observed live):** "start a 360 for Vera and draft her review" → send → ONE action
proposed (the review half silently dropped) → approve → one line of text, no link, no navigation,
no visible execution, async draft invisible. The write is real; the experience says "nothing
happened." This file fixes the experience WITHOUT touching the gate.

**The target demo story (must work end-to-end when done):**
Ada types "start a 360 for Vera and draft her review" → Send → a 2-step plan appears with a
one-line grounded reason under each step → Ada clicks **Approve all & run** → Step 1 spins
("Creating 360 cycle…") → ✓ result card "360 cycle created — Vera Lindqvist · Draft" with
**Open →** → Step 2 spins ("Drafting review with AI… ~20s", live job tracking) → ✓ "Draft ready —
pending your review" with **Open →** → completion summary: "2 of 2 done. The review draft is
waiting for your approval." + suggestion chip "Invite reviewers for Vera's cycle?" → Ada clicks
Open → lands on the review.

## Iron invariants (unchanged — restate, do not weaken)
- Every write still executes ONLY via the existing per-step approve endpoint; server re-checks
  capability + scope per step; params resolved server-side; embedded text is data.
- "Approve all & run" is FRONTEND-ONLY sequential orchestration over the existing endpoint —
  the backend gate does not change. If a step fails, stop; remaining steps stay pending.
- No auto-execution without an explicit human click. Deep links are plain client routes.
- Real data only; honest empty states.

## A. One send path — everything is a plan (backend + frontend)
- POST /api/ai/chat: a write-intent message now returns a PLAN (type:"plan") instead of a single
  proposal. Single intent → 1-step plan; multi-intent (the planner's clause split) → N steps.
  Read intents unchanged.
- Remove the dual send/plan buttons in the panel — ONE send button. A 1-step plan renders
  compactly (like today's confirm card); multi-step renders the checklist. Reason shows as a
  muted subtitle under each step (not hidden behind a click).
- If part of the message can't be planned (unknown/forbidden/ambiguous), the plan's summary SAYS
  so in one plain sentence — nothing silently dropped. Ambiguity → a clarify step with candidates.
- CONTRACT CHANGE IS DELIBERATE: update the affected tests + smoke assertions ("chat
  write-blocked" → "chat write→plan, inert, zero executions"). This is a product change, not a
  red suite. Keep: plan creation writes nothing (assert audit unchanged on plan-create).

## B. Rich result cards + deep links (backend + frontend)
- execute_action result contract: add an `artifact` object per action:
  { type, id, title, state, deeplink } — e.g. initiate_360 → {type:"feedback_cycle", title:"360 —
  Vera Lindqvist", state:"DRAFT", deeplink:"/feedback?cycle={id}"}; draft_review →
  "/reviews/{review_id}"; give_recognition → "/recognition"; record_actual / update_kpi_actual /
  approve_goal → "/goals?person={employee_id}"; open_checkin / respond_to_checkin → "/checkins";
  career_enrich → "/career"; succession_enrich → "/succession". VERIFY each route exists in the
  router first — reuse real routes only, never invent; adjust query params to whatever the screen
  actually reads. Backend test per action asserts artifact presence + a valid deeplink.
- Frontend: an executed step renders a ResultCard — icon by artifact type, title, state pill, and
  a primary **Open →** (react-router navigate). Single-step plans: the approve button becomes
  **Approve & open** (navigates on success). Multi-step: each ✓ card has Open; the completion
  summary has the primary Open for the last/primary artifact.

## C. Live async job tracking in chat (frontend, reuse existing job API)
- draft_review / career_enrich / succession_enrich return a job_id. The chat must TRACK it: the
  step card shows "Working… (AI drafting)" and polls the SAME job-status endpoint the screens
  already use (find it — AIJobBanner/screen polling; do NOT invent a new endpoint; if none is
  exposed, add a read-only scoped GET /api/ai/jobs/{id} with owner+tenant checks + tests).
- On job completion: flip to ✓ with the artifact card (fetch the artifact state); on job failure/
  degrade: an honest amber card "AI unavailable — nothing was changed" (never fake success).

## D. "Approve all & run" (frontend only)
- Multi-step plans get one **Approve all & run** button next to per-step approves. It executes
  steps SEQUENTIALLY via the existing approve endpoint, updating each card live. Clarify steps
  pause the run (fill the picker → continue). A failed step stops the run; the rest stay pending.
- RTL test: 3-step mocked plan → run-all fires 3 sequential approve calls in order, renders
  spinner→done per step, stops on a mocked failure at step 2 (step 3 never called).

## E. Completion summary + suggested next step (frontend + tiny backend)
- After the last step: a summary bubble — "N of N done" + linked artifact list + pending async
  note. Plus ONE suggestion chip when an obvious next action exists in the registry (e.g. after
  initiate_360 → "Invite reviewers"; after draft_review → "Open the draft"). Chips only PREFILL
  the input — they never auto-send. Suggestion mapping is a small static table per action —
  no LLM call.

## F. Panel persistence + session resume (frontend)
- The chat panel must survive in-app navigation (keep mounted in the shell). On app reload or
  panel reopen within TTL, resume the most recent session via the existing sessions API (history
  visible, references still resolve). One RTL test: reopen renders prior turns from a mocked
  session.

## G. STRETCH (only if A–F are green and time remains): page context awareness
- Frontend sends page_context {route, entity_type, entity_id} with each message; backend
  resolve_person_reference MAY use it as a resolution hint — with the SAME live access re-check
  (never widens scope; out-of-scope context is ignored). Tests: in-scope context resolves "this
  person"; out-of-scope context is ignored + generic clarify. If risky or slow → flag + skip.

## PART 2 — the four demo fixes (from this morning's review; unchanged in intent)
1. **Ask AI visibility:** first-class "Ask AI" button (sparkle icon) in the TOP BAR of every page,
   between the bell and the ? — opens the panel. Fix the panel subtitle (it still claims
   read-only/never-makes-changes — factually wrong now): "Ask questions or plan multi-step tasks —
   I propose, you approve each step. Nothing runs without your OK."
2. **Analytics history:** extend seed_demo_rich with THREE prior scored cycles (Q4 2025, Q1 2026,
   Q2 2026 + current H1) — real Cycle rows, real recorded actuals, real T-scores via the actual
   scoring pipeline, believable per-person variation. Individual trend = 4-point curve; Department
   aggregates; Calibration grid gets a real distribution.
3. **Goals realism + clarity + life:** role-appropriate KPI names in the seed (PM: "Ship 3
   features by end of H1", "Feature adoption > 40%"; Eng: "Merge cycle time < 3 days",
   "Post-release incidents 0"; Design: "Design reviews within SLA 95%+") — no more
   Impact/Throughput/Quality shells. Relabel UI jargon: "actual"→"Progress", "Increasing is
   better"→"Higher = better ↑" (and ↓ variant); tooltips on Goal weight + T-score (plain one-
   liners). Add a **GoalUpdate** model (TenantScopedModel, audited, migration + 3 tests: create /
   tenant isolation / audit) + an "Updates" timeline under each goal card; seed 2–4 realistic
   updates per active goal ("Shipped v2 of the pricing page — Vera, 3 days ago").
4. **Current-cycle actuals:** seed recorded actuals for ≥60% of current-cycle KPIs (varied: some
   ahead, some behind) so progress bars + T-scores are real computed values, not "not recorded".

## Branches / merge
- Backend (plan-by-default, artifact contract, GoalUpdate, seed, jobs endpoint if needed): main,
  auto-merge on green.
- Frontend agent UX (A–F, Ask AI button, labels/tooltips, updates timeline): hari/agent-ui-v2
  (extend the existing branch — same feature, keep it reviewable in one place).
- Live AI allowed for verifying the demo story end-to-end once (gpt-4o-mini, ≤10 calls total).

## Definition of done
- The target demo story runs live end-to-end exactly as written above (do it once yourself with
  live AI and paste the transcript into REVIEW_NOTES.md).
- ./scripts/demo_ready.sh green with the UPDATED plan-flow assertions (write→plan inert; artifact
  + deeplink present; run-all executes exactly the approved steps; injection still executes
  nothing — goal.approved unchanged).
- Backend + frontend suites green; new tests per section above; REVIEW_NOTES.md updated with the
  exact click path; MORNING_HANDOFF_JULY3.md appended.
- Anything ambiguous → HARI_ATTENTION_NEEDED_agentux_<topic>.md, keep moving. Never push red.
