# FINAL_REPORT — v1 completion + production handover (FINAL.md run)

Run of 2026-07-13, branch `hari/agent-ui-v2`, base `1f77c8e`. Everything below was implemented,
tested, and verified against the running app in this run. Honest partials are listed in §What remains.

## 1. What was fixed (by section, with commits)

**D — RBAC "visible but unauthorized" (top priority) — `51eaeeb`**
- Root cause: the client had NO capability data (`/me` returned only `role`); action buttons relied on
  hand-written `atLeast` gates, and the biggest one (Reviews) had none.
- `/api/auth/me` now returns `capabilities` computed from the SAME matrix the server enforces
  (`capabilities_for_role`, locked by a mirror-test); `AuthContext.can(capability)` is the single gate.
- **Reviews ActionBar** (the #1 offender): every button (AI draft / start-edit / edit / approve /
  reject / finalize / revise / save / submit) now capability-gated; an Employee gets a clean read-only
  page (unit-tested via `visibleReviewActions`). The EDITING editor is read-only without
  `manage_reviews`.
- **Scope-checked pickers** unified on a new `useScopedPeople()` hook (mirrors `actor_can_access`):
  create-review, create-360-cycle, analytics employee/head, and goals (refactored onto the hook). No
  more "pick → 403 outside your access scope".
- Server-side enforcement untouched (defense in depth verified live: employee approve → 403).
- Docs: `RBAC_MATRIX.md` (full server-grounded matrix) + `AUTHZ_UI_ISSUES.md` (every finding + fix).

**E — Chat copilot UX (top priority) — `d7e20bb`**
- E1: drag-to-resize panel (320–720px, persisted to localStorage, a11y `role="separator"` handle).
- E2: the panel was already shell-mounted/non-modal (survives navigation, no outside-click dismiss);
  added true side-by-side — the content column shrinks by the panel width (≥sm), so "AI says go to X →
  click → page loads beside the still-open chat" works. Doc: `AGENT_CHAT_UX.md`.

**B — Auth fixes — `fee090a`** (review: `AUTH_REVIEW.md`)
- **Logout now actually revokes**: the client sends the refresh token (captured before clearing);
  verified live — logout 205, refresh replay 401.
- **Real MFA un-broken**: client/server field mismatch fixed (`mfa_token`, `config_url`); MSW mocks now
  mirror the REAL backend shape so tests exercise the true contract.
- Session-cookie hardening pinned explicitly in prod (`HTTPONLY`, `SAMESITE=Lax`).

**C — Agent memory — `2e20745`** (review: `AGENT_MEMORY_REVIEW.md`)
- Read/Q&A path now uses the conversation: intent classification sees recent turns (context-only
  block); pronouns resolve via the same access-rechecked session refs the plan path uses; read answers
  ground a `user` ref; **named people resolve** ("how is Vera doing?" answers about Vera, not you);
  **count-questions get real counts** ("how many reviews do I have" — previously a goals-dump misroute).
- Frontend: `session_id` persisted; the conversation rehydrates from the 24h server session on reload.
- Scope-safety proven by tests + live probe (peer asking about Vera → "No data in your scope").
- 4 new backend tests; verified LIVE on Gemini (pronoun follow-up returned Vera's real review count).

**F — Production handover package — `aad7676`, `01418a0`**
- **Email/SMTP wired** (was completely absent): `EMAIL_*` settings + console default for dev.
- **Self-service password reset built** (was missing entirely): tenant-qualified request (always-200,
  no enumeration) → emailed single-use link → confirm (validators enforced, audited, **revokes all
  outstanding refresh tokens**); frontend "Forgot password?" + `/forgot-password` + `/reset-password`
  pages; 4 backend tests incl. session-revocation and no-enumeration.
- **`.env.example` rewritten production-grade**: every variable the app reads, verified against
  `config/settings/prod.py`; `[PROD]` vs `[dev only]` marked (settings module, DEBUG=false, real
  domains — never `*`, `LLM_MAX_CALLS` sized for tenants or 0 + provider cap, real `FLOWER_BASIC_AUTH`);
  previously-missing prod vars added: `METRICS_TOKEN`, `DB_REPLICA_*`, **`DB_SSL_CA` (newly wired
  MySQL-TLS option)**, `EMAIL_*`, `PUBLIC_APP_URL`, `SENTRY_*`, JWT lifetimes, throttles, gunicorn.
- **`DEPLOYMENT_HANDOVER.md`**: managed MySQL (backups/PITR, connection sizing, TLS, optional replica),
  managed Redis ×2 (broker noeviction vs cache lru — why one instance can't do both), web/worker/beat
  topology, TLS/LB, `deploy_migrate` release step, seeding, monitoring (/metrics token + Sentry), and
  the honest not-production-wired list. **Gemini confirmed wired + working live.**

**A — Review & QA**
- `PROJECT_ASSESSMENT.md`: all 17 modules classified with evidence; P0s (email/reset, logout, MFA,
  authz-UI) all fixed this run; the remaining honest gaps are notifications (Slack-only) + the
  documented P1s.
- `QA_CHECKLIST.md`: verified record — 57/57 E2E smoke + **9/9 live probes** of this run's fixes +
  the suites; ◻ human-only items listed.

## 2. What remains / couldn't be done (and why)
- **In-app notifications** — no notification system exists (Slack-only, silent no-op). A v2 build
  (model + feed + preferences), not a pre-handover patch. Documented everywhere it matters.
- **Refresh-token storage + per-account lockout** — accepted v1 risks with mitigations (15-min access,
  rotation/blacklist, revoke-on-logout/reset, IP throttle); the full fixes are v2 decisions
  (`OPEN_QUESTIONS.md` #1–2).
- **Manager self-approval** (server permits; UI mirrors) — a product decision, not changed unilaterally.
- **UI-stricter-than-server capabilities** (org chart/analytics/approvals for employees, JD for
  managers) — widening scope is a product call; listed in `OPEN_QUESTIONS.md` #5.
- **Mobile** — deferred to v2 (unchanged; `docs/handoff/MOBILE.md`).

## 3. Human testing checklist (log in as each role: admin@ / priya@ / ada@ / akhil@acme.test · `Passw0rd!demo` · :8090)
1. **No unauthorized walls:** as **akhil (Employee)** open your review → NO action buttons (clean
   read-only); Goals → no New-goal/Approve; Analytics/Audit/Admin absent from nav. As **ada (Manager)**
   the New-goal / New-review / New-cycle pickers list ONLY her team; every visible button works without
   a 403.
2. **Chat copilot:** open Ask AI → drag its left edge to resize → navigate pages — it stays open beside
   the page; reload — the conversation is still there.
3. **Agent memory:** ask "how is Vera doing on her goals?" then "how many reviews does she have?" —
   the second answer is about Vera with a real count. As akhil, ask about Vera → scope-refused.
4. **Auth:** logout, then verify you can't refresh back in (revoked). Login "Forgot password?" → with
   SMTP configured (or the console backend log) follow the link → set a new password → old sessions dead.
   Enroll MFA (Settings) and complete a TOTP login — first run on the real contract.
5. **Every module's core path:** create/edit a goal + record progress (bar updates live), draft →
   approve → finalize a review (as ada/priya), open+respond a check-in, run a 360 cycle, post
   recognition, approve an inbox step, JD generate (fill inputs first), admin user CRUD (as admin).
6. **JD trap check:** as priya, create a NEW JD and hit Generate — confirm the UI collects inputs
   before enabling it (else it 422s by design).

## 4. Open questions
See `OPEN_QUESTIONS.md` (9 product decisions + rough edges), `AUTHZ_UI_ISSUES.md` §by-design, and
`DEPLOYMENT_HANDOVER.md` §7 (the not-wired list).

## 5. Green + handover confirmation
- Frontend: `tsc` clean · **132 vitest** (incl. new gating + org tests) — verified this run.
- Backend: full suite green (1437+ incl. 4 reset + 4 memory + 1 capabilities tests; identity 51 /
  ai 243 / rbac+identity 377 / goals+budgets 111 verified individually; full-suite log:
  `scratchpad/full_backend_final.log`).
- Live: **57/57 E2E smoke** (demo_ready) + **9/9 targeted QA probes** on the running stack (live Gemini).
- Handover package complete: **`.env.example`** (production-grade, placeholders only) +
  **`docs/V1_REVIEW/DEPLOYMENT_HANDOVER.md`** + the `docs/handoff/` engineering set.
