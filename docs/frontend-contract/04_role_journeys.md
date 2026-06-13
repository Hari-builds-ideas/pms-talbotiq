# Frontend Contract — 04 · Primary Role Journeys

The end-to-end flows the frontend must make smooth, as ordered screen + action
steps. **[D]** = Desktop Hub, **[M]** = Mobile-Web, **🔒HITL** = a human-gate the UI
must surface (never auto-advance). Screen/endpoint detail is in `01_screens.md`;
transitions in `02_state_machines.md`.

---

## A. Employee — self-service cycle (mostly [M])
1. **[M] Login → Dashboard.** `POST /api/auth/login` (+ MFA if enabled) → `me` →
   employee dashboard tiles.
2. **[M] Update KPI actuals.** Goals screen → enter actuals → `POST` own actual.
   *Validation:* own KPIs only (a peer's → 404); weights already fixed at goal time.
3. **[M] Give 360 feedback.** "Requests" → open a PENDING invitation → write →
   `…/give` (request → SUBMITTED). The UI never shows other givers; the subject's
   identity is the only attribution.
4. **[M] Read own finalized review.** Reviews → own review. Only readable once
   **FINALIZED**; before that it shows "in progress / pending review" (🔒HITL — the
   employee does NOT approve their own review).
5. **[M] View own career roadmap.** Career → select a target role (PUBLISHED JD or
   Position) → deterministic skill-gap + tiered roadmap → mark tier progress. The
   roadmap is **advisory** (never a promotion) and shows **no succession data**.
6. **[M] (optional) Ask the Chat panel.** Read-only answers within the employee's own
   scope; write requests are refused. (503 if AI isn't live yet.)

*Crosses surfaces:* none — fully Mobile-Web. *HITL gate:* the employee waits on the
manager's review approval (step 4).

---

## B. Manager — review + approvals + team (mostly [D]; own self-service on [M])
1. **[D] Open the review cycle.** Reviews list (scoped to the team) for the ACTIVE
   cycle; create a report's review if needed (requires an ACTIVE cycle).
2. **[D] Draft → 🔒approve a report's review.** Either request an AI draft
   (DRAFT→AI_DRAFTING→PENDING; needs the `agent1` feature = FULL_AI, else 503/403) or
   start-edit → submit (EDITING→PENDING). Then **🔒HITL: Approve** (PENDING→APPROVED,
   sets you as `human_reviewer`) or **Reject** (reason required). The UI shows the
   draft badge + confidence + low-confidence warning and never presents it as final.
3. **[D] Finalize.** APPROVED → finalize → **FINALIZED** — UNLESS an approval route is
   active, in which case it enters the route (a stepper appears).
4. **[D] Act on the approvals inbox.** Inbox shows steps assigned to you (SEQUENTIAL =
   only the active step). Approve / Reject(comment) → the route advances/ends. Watch
   the route tracker stepper. (409 if out-of-order / already decided → re-fetch.)
5. **[D] See team analytics.** Department analytics for your line (`?head=you&cycle=`).
   **If your team < 5 members → aggregate-only (individuals suppressed)** — the UI must
   honour `suppressed` and show the "cohort too small" marker.
6. **[D] Manage succession for your tier.** Add bench candidates / assess 9-box for
   your own reports (out-of-tier → 404). Generating/publishing a plan is HRBP+ (you'll
   get 403 — hide those controls).
7. **[M] Own self-service.** Your own goals/actuals, own review (read), own career
   roadmap — same as Journey A.

*Crosses surfaces:* management on [D], own self-service on [M]. *HITL gates:* steps 2
(review approve) + 4 (approval steps).

---

## C. HRBP — talent governance ([D])
1. **[D] Feedback summary review/release.** Review queue → a summary in
   **HRBP_HOLD** (breach/sensitive) or PENDING → read the anonymised payload (no
   givers) → **🔒Approve/Release** (→ RELEASED, then the subject can see it). Sections
   are NULL until Agent 3 ran — never fabricate; "not generated" is a valid state.
2. **[D] Succession plan review/publish.** Dashboard (tenant-wide) → mark critical
   roles + knowledge risk → generate analysis (→ PENDING_HUMAN_REVIEW) → add action
   items → **🔒Publish** (→ PUBLISHED, appears on the dashboard with coverage RED/
   AMBER/GREEN). Optionally enrich with Agent 4 (→ a *new* AI plan PENDING for
   re-review; 503 if not live). Publish only from PENDING (else 409).
3. **[D] Calibration grid.** 9-box grid for a cycle (HRBP/Admin only) — counts per box
   + placements, to calibrate ratings across the tenant.
4. **[D] (scoped) Audit console.** Read-only, filterable history for oversight.

*Surface:* Desktop only. *HITL gates:* steps 1 (summary release) + 2 (plan publish) —
both are required human approvals of AI/automated output.

---

## D. Admin — tenant setup + commercial ([D])
1. **[D] Create users + assign roles.** Admin → Users → create ({email, role,
   manager?}) → set role / set reporting line (cycle-checked → 422) / deactivate.
   (422 EMAIL_TAKEN / UNKNOWN_ROLE; 404 on a cross-tenant id.)
2. **[D] Configure approval workflows.** Workflow designer → define SEQUENTIAL/PARALLEL
   steps (ROLE/NAMED approvers, timeouts, escalation) → activate (at most one active
   per artifact_type). This drives the routes Managers/HRBP act on in Journey B/C.
3. **[D] Entitlements + upgrade.** Billing → see the feature-flag map + locked premium
   features → set seats (independent of packs) → **Upgrade to FULL_AI** (flips every
   premium flag instantly — incl. Agent 1 — without changing seats). The upgrade modal
   (`upgrade-prompt`) lists what unlocks (conceptual; no payment).
4. **[D] Integrations.** Configure Jira / Slack: enable + non-secret config + a
   `secret_ref` (env-var NAME — never a raw token). Unconfigured = clean no-op.
5. **[D] Audit console.** Tenant-wide read-only history; nothing is mutable.

*Surface:* Desktop only. *No HITL gates* (config actions), but every write is audited
(visible in step 5).

---

## Cross-cutting journey notes
- **Surface split:** management/configuration journeys (B-management, C, D) are
  Desktop; self-service (A, B-own) is Mobile-Web. **Succession never appears on
  Mobile-Web and never for an Employee (404).**
- **Every AI/automated artifact passes a human gate** before it's "real": review
  approve→finalize, feedback summary release, succession plan publish, JD approve→
  publish, AI career roadmap acceptance. Build the approve/reject/publish affordances
  as first-class steps, not afterthoughts.
- **Premium prompts:** when a journey hits a FULL_AI-only feature on a STARTER tenant
  (Agent 1 draft, JD generate, career enrich, agents 3-5), show the locked state +
  the upgrade path — not a dead end.
