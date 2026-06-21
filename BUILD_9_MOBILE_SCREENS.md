# BUILD_9 — Mobile self-service screens (Mobile Phases 2–7)

> Read BUILD_0_READ_FIRST.md + MOBILE_BUILD_PLAN.md first; all rules apply. Build 4 of the final push.
> Builds on BUILD_8's scaffold/auth/shell/dashboard. Each screen: real API via the shared client, the
> shared RBAC/feature-flag/error-mapper conventions, all states (loading/empty/error-by-code/offline/
> pending-HITL/locked-by-flag/404-out-of-scope), NativeWind on the shared design tokens. Each phase: runs
> in Expo + typecheck/lint clean → commit + push → BLOCKER protocol if stuck. Almost zero LLM calls
> (reuse seeded artifacts; never burn Groq). Mobile is the SELF-SERVICE surface — NO admin/succession/
> analytics/org-editor/JD-authoring (those stay web-only, per the plan).

---

## Phase 9.1 — My goals + record actuals (Mobile Phase 2)
View my goals/KPIs; record an actual on a KPI (own-only). Optimistic update + the 409 stale-version
handling from BUILD_4; on recompute, the risk/score reflects. Endpoints: `goals.list`,
`goals.recordActual`. **Verify [live]:** record an actual on the device → score updates after recompute.
Commit `BUILD_9 9.1 — mobile goals + actuals`.

## Phase 9.2 — My review + self-assessment (Mobile Phase 3)
View my finalized review (HITL/confidence rendering preserved if a draft is visible); submit my
self-assessment. Endpoints: `reviews.detail`, `reviews.assessments`, `reviews.upsertAssessment` (SELF).
**Verify [live]:** view a finalized review + submit a self-assessment. Commit `BUILD_9 9.2 — mobile review
+ self-assessment`.

## Phase 9.3 — 360: give feedback + my summary (Mobile Phase 4)
Respond to feedback invitations (the giver surface); view MY released 360 summary via
`feedback.myCycles` → `feedback.summary`. The anonymity + min-volume copy is visible; a below-threshold
group shows suppressed; never any giver identity; 403 until released. **Verify [live]:** give feedback as
an invited giver; view my released summary; suppressed group shows correctly. Commit `BUILD_9 9.3 — mobile
360 give + my summary`.

## Phase 9.4 — My career roadmap + progress (Mobile Phase 5)
View my roadmap (tiers + skill gap), mark per-tier progress, select/change target. Enrich-with-AI gated
by the `career_roadmap` flag (STARTER shows the upgrade affordance). Endpoints: `career.roadmap`,
`career.progress`, `career.setProgress`, target select. **Verify [live]:** view roadmap + mark progress;
the AI enrich is gated correctly by tier. Commit `BUILD_9 9.4 — mobile career`.

## Phase 9.5 — AI chat (Mobile Phase 6)
The read-only, RBAC-bound assistant: grounded answers within scope, out-of-scope returns nothing, write
intent blocked, 503/429 graceful. Endpoint: `ai.chat` (sync, per D6). **Verify [live]:** an in-scope
grounded answer, an out-of-scope empty, a write intent blocked. Commit `BUILD_9 9.5 — mobile chat`.

## Phase 9.6 — Manager extras (Mobile Phase 7)
For manager-role users on mobile: my team's nudges, approve my reports' goals, act on my approval inbox
(approve/reject-with-reason), and request an AI review draft for a report (fire→poll via the shared
`useAIJob`, lands PENDING for the human gate). Manager scope only; respects every RBAC/scope rule.
Endpoints: `ai.nudges`, `approvals.inbox`, approve/reject, `goals.approve`, `reviews.requestAiDraft` →
poll. **Verify [live]:** a manager approves a report's goal + acts on an approval + fires an AI draft that
lands PENDING. Commit `BUILD_9 9.6 — mobile manager extras`.

## Phase 9.7 — Notifications (in-app) + the device-register endpoint (push prerequisite)
- In-app notification center from existing real counts (nudges / approvals-awaiting / feedback-requested
  / summary-released) — no new backend needed for the in-app view.
- Add the ONE genuinely new backend endpoint the readiness gate flagged: `POST /api/devices` to register
  a device push token (tenant-scoped, own-user, tested). WIRE `expo-notifications` registration to it.
  Actually delivering push (a push service) is infra — out of scope; the endpoint + registration is the
  code-ready part.
**Verify [test]+[live]:** in-app notifications show real counts; the device-register endpoint accepts a
token (scoped, tested); expo-notifications registers. Commit `BUILD_9 9.7 — mobile notifications + device
register`.

## Phase 9.8 — Mobile hardening
- Offline posture (React Query cache + a clear offline banner; queued writes for record-actual/give-
  feedback/self-assessment with optimistic + retry, per the plan).
- RN component tests for the risky screens (the goals 409 path, the AI-job polling state, the 360
  suppression rendering, RBAC/flag gating). Typecheck/lint clean.
- Confirm the whole mobile app runs in Expo against the live backend, every screen real, no dead buttons.

**Verify [test]+[live]:** offline banner + queued write works; RN tests green; full app runs live. Commit
`BUILD_9 9.8 — mobile hardening`.

---

## End of BUILD_9 (and the final push)
Write `BUILD_9_REPORT.md` AND `FINAL_PUSH_COMPLETE_REPORT.md` covering BUILD_6–9: the web stabilization +
the two Tier-3 features + the mobile app (Phases 0–7 + hardening) as-built, what is verified [test]/
[live]/[build], the full commit/push list, all QUESTIONS/DECISIONS/BLOCKER, final backend + frontend +
mobile test counts, and an HONEST statement of what is production-complete vs what still needs (a) infra
provisioning, (b) the Gemini key, (c) EAS build + store accounts for an actual mobile release (release-
time only, per the plan), and (d) any mobile screen not finished in the window. Be scrupulously honest
about live-verified vs build-only — especially for mobile, where "runs in Expo against the backend" is
the real bar, not "compiles".
