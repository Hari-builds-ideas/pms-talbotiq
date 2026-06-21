# MOBILE_BUILD_COE — the COE Engagement Hub on mobile (incl. 1:1 Meeting Notes)

> Read BUILD_0_READ_FIRST.md, COE_REQUIREMENTS_MAP.md, MOBILE_BUILD_PLAN.md, MOBILE_MOCK_ADAPTATION.md
> IN FULL first. This runs on Hari's Mac (Expo runtime). All BUILD_0 rules apply. The brief's Mobile row
> is the rubric: "Engagement Hub: Continuous Feedback, 1:1 Meeting Notes, Goal Tracking, 360 Quick
> Assessments, 1-Click Approvals." This build delivers all of it, adopting the PMS_MOBILE mock's look
> (the approved adaptation plan), on Expo SDK 54 (matching the Expo Go on Hari's iPhone).
>
> ACCEPTANCE BAR for every screen: RUNS in Expo Go SDK 54 on Hari's iPhone (or the iOS simulator) against
> the live backend — NOT "compiles". After each screen: `cd mobile && npx expo start`, then STOP and tell
> Hari exactly what to open/tap and what to expect; wait for his device report before the next screen.

First make sure the foundation from the prior session is solid: SDK 54 pinned, the `pmsshared` imports
resolve in Metro on-device, secure-store guarded for web, login loads on the device. If any of that
regressed, fix it before new screens.

---

## Phase M1 — 1:1 Meeting Notes (NEW backend + mobile screen) — the brief gap

This is required by the brief and currently has NO backend. Build it backend-first with tests, then the
mobile screen.
- **Backend:** a tenant-scoped `OneOnOneNote` (or `MeetingNote`) model: tenant FK, the manager (author),
  the report (subject), date, body/agenda, optional shared-vs-private flag, optional linked goal/review,
  created/edited timestamps. RBAC: a manager creates/reads notes for their own reports (scope-bound); an
  employee sees notes shared WITH them per a clear visibility rule (decide in DECISIONS.md — default:
  manager authors; a note is private to the manager unless explicitly shared with the report). Audited.
  Cross-tenant → 404, out-of-scope → 404/403 per the existing conventions.
- Endpoints: list (scoped to the 1:1 relationship), create, edit/delete own, mark shared. Add to the
  RBAC matrix (new capability or reuse a manager capability — justify). Tests: scope (a manager can't
  note another manager's report), tenant isolation, the shared-visibility rule, audit row written.
- Add to the shared API client (`pmsshared`) so both web (later) and mobile use one client.
- **Mobile screen:** a 1:1 Meeting Notes screen in the engagement hub — list my 1:1s (as manager: per
  report; as employee: notes shared with me), create/edit a note, all states. Mock look.

**Verify [test]+[live]:** backend scope/tenant/visibility/audit tests green; the mobile screen creates +
lists a real note on the device; an out-of-scope user can't see it. Commit `MOBILE_COE M1 — 1:1 meeting
notes (backend + mobile)`.

## Phase M2 — Goal Tracking (mobile)
View my goals/KPIs + record actuals (own-only, optimistic + 409-aware), see attainment/progress. Mock
look, real endpoints (`goals.list`, `goals.recordActual`). **Verify [live]:** record an actual on-device
→ score reflects after recompute. Commit `MOBILE_COE M2 — goal tracking`.

## Phase M3 — 360 Quick Assessments (mobile)
The brief's "360 Quick Assessments": respond to feedback invitations quickly (the giver surface), and
view my released 360 summary (via `feedback.myCycles` → `summary`). Anonymity + min-volume copy visible;
no giver identity ever; 403 until released; below-threshold group suppressed. **Verify [live]:** give
feedback as an invited giver; view my released summary; suppression shows. Commit `MOBILE_COE M3 — 360
quick assessments`.

## Phase M4 — Continuous Feedback (mobile)
The brief lists Continuous Feedback distinct from cycle-360: give/receive continuous feedback (the
existing continuous-feedback endpoints), my feedback inbox. Mock look. **Verify [live]:** give a piece of
continuous feedback; it appears for the recipient per scope. Commit `MOBILE_COE M4 — continuous feedback`.

## Phase M5 — 1-Click Approvals (mobile, manager)
The brief's "1-Click Approvals": a manager's approval inbox with approve / reject-with-reason in one tap,
the tracker, plus approve a report's goal. Manager scope only; respects RBAC/escalation. Endpoints:
`approvals.inbox`, approve/reject, `goals.approve`. **Verify [live]:** a manager approves an item in one
tap and rejects another with a reason; tracker advances. Commit `MOBILE_COE M5 — 1-click approvals`.

## Phase M6 — Engagement-hub glue: Home/dashboard, AI (nudges+chat), notifications, More
- Home/dashboard (mock layout, real data: me, my cycle score, goals, pending feedback, nudges).
- AI tab = real `ai.nudges` + `ai.chat` (read-only, RBAC-bound, write-blocked) — NOT a faked AI summary.
- Notifications from real counts (feedback-requested, approvals-awaiting, summary-released, nudges) + the
  `POST /api/devices` device-register endpoint for future push (wire expo-notifications registration).
- More: identity, features, sign out.
**Verify [live]:** each tab shows real data on-device; chat grounded/out-of-scope/write-blocked. Commit
per screen `MOBILE_COE M6a..` .

## Phase M7 — Mobile functional verification + hardening (the brief's testing row, mobile side)
- Verify on mobile-web/device the brief-graded behaviours that apply to the engagement hub: KPI=100%
  validation surfaced where goals are edited, approval escalation visible, review-cycle/feedback
  transitions reflected, notifications fire. Add to docs/FUNCTIONAL_TEST_MATRIX.md (the mobile rows).
- Offline posture (cache + offline banner; queued writes for record-actual/give-feedback/1:1-note),
  RN component tests for the risky screens (goals 409, AI-job poll if used, 360 suppression, RBAC gating).
**Verify [test]+[live]:** RN tests green; offline works; the mobile functional rows are proven. Commit
`MOBILE_COE M7 — mobile functional verification + hardening`.

---

## End of MOBILE_BUILD_COE
Write `MOBILE_COE_REPORT.md`: every engagement-hub feature as-built (incl. 1:1 notes backend+screen),
what's verified on-device [live] vs [test]/[build], the commit list, QUESTIONS/DECISIONS/BLOCKER, test
counts, and an honest statement of what remains (EAS build + store accounts for a real release — release-
time only; the 🔑 infra items). Be scrupulously honest: "runs on my iPhone in Expo Go" is the bar, and
only Hari's device report can confirm it — record which screens he confirmed vs which are build-only.
