# PROJECT_ASSESSMENT — module-by-module, production-handover review

Grounded in code (evidence files cited). Written 2026-07-13. Classifications:
**Complete / Partial / Missing / Broken / Risky.**

**Overall:** a genuinely well-built codebase — 100+ backend tests, consistent tenant-scoping/RBAC seams,
deterministic 360 anonymization, append-only audit, graceful AI degradation, and no meaningful TODO/stub
debt in product code (one intentional `HTTPLLMProvider` stub). It is **not** mock-driven (mocks gated
behind `VITE_USE_MOCKS`, default false). The production-blocking gaps are concentrated in the
**cross-cutting communication layer** — email (Missing), password reset (Missing), notifications
(Slack-only) — not in the core PMS flows.

| # | Module | Verdict | Evidence / what's wrong |
|---|---|---|---|
| 1 | Login/auth | **Partial → fixed this run** | Backend solid: login/refresh/logout/me, real TOTP MFA, OIDC+SAML seams (`apps/identity/`). Gaps found: **no password reset** anywhere; **logout didn't revoke** (client empty-body vs required `refresh`); **MFA client/server field mismatch** (`mfa_token` vs `challenge`) → real MFA broken. All three fixed this run (see AUTH_REVIEW.md). |
| 2 | Dashboards (per role) | **Complete** | All four cockpits wire real endpoints (`cockpit-roles.tsx`, `tiles.tsx`); loading/tone states; AI tiles gated by `hasFeature("agent2")`; hidden-in-v1 tiles not fetched (clean). |
| 3 | Goals & OKRs | **Complete** | Full CRUD + approve + actuals + updates timeline + AI draft (`apps/goals/`, 7 test files). The three BUGS_GOALS.md fixes verified present (`serializers.py:43,62`; picker scope in `GoalsPage.tsx`/`lib/org.ts`). |
| 4 | Reviews | **Complete** | Single-source state machine w/ legality+RBAC+audit per transition (`apps/reviews/state_machine.py`); AI draft via HITL seam; sections/assessments/comments/finalize; 6 test files. |
| 5 | Check-ins | **Complete (lightest tests)** | Employee loop + manager respond + meeting summary; own-or-manager scope (`apps/checkins/views.py:61`). Only 1 backend test file — P1: broaden coverage. |
| 6 | Feedback/360 | **Complete (highlight)** | Cycles/give/requests/decline; deterministic per-group min-volume anonymization (`apps/feedback/anonymize.py`, MIN=3) + identity-leak scan; AI summary behind a release gate (HITL). |
| 7 | Recognition | **Complete** | Post/feed/react; visibility enforced server-side (`services.recognition_feed`). |
| 8 | Employees/Org | **Complete** | Tree/search/export/vacancies/positions CRUD/reassign; profile page; lazy org tree. |
| 9 | JD Library | **Complete (one UX trap)** | Full lifecycle + async AI generate. The known 422: `validate_generation_inputs` hard-422s when a DRAFT's `inputs` snapshot is empty (`apps/jd/views.py:234-244`) — **by design** (fail fast, no doomed job), but if the UI enables Generate on a bare DRAFT the user hits a 422 wall. Checked in this run's QA (A2) + D2 sweep. |
| 10 | Analytics | **Complete (v1 scope cut)** | Individual trend + department; calibration/nine-box + T-score deliberately hidden (`frontend/src/app/v1.ts`) — retained for v2, documented. |
| 11 | Notifications | **Partial / Risky** | **No first-class notification system** — no notifications app/model/center; the Topbar bell is not backed by a feed. Only best-effort Slack (`apps/integrations/notifications.py`) which silently no-ops without a webhook. In a Slack-less tenant, approvals/feedback-requests/escalations reach no one. Biggest functional gap after email — flagged honestly in the handover; building an in-app center is a v2 project, not a pre-handover patch. |
| 12 | Chat/agent | **Complete (memory gap fixed this run)** | Plan→approve genuinely inert-until-approved, double capability checks, destructive-verb guard. Read/Q&A path had no memory + misrouted count-questions — fixed this run (see AGENT_MEMORY_REVIEW.md). All AI 503s cleanly until a provider key is set. |
| 13 | Settings/admin | **Complete (v1 scope cut)** | Users CRUD/role change/deactivate, stats, entitlements; raw tenant-config hidden in v1. |
| 14 | Approvals | **Complete** | Workflows CRUD, inbox, step approve/reject, escalation engine + Celery beat; escalation *delivery* inherits the Slack-only limitation (module 11). |
| 15 | Audit | **Complete** | Genuinely append-only (`save()` refuses rewrites, manager forbids update/delete); console UI. |
| 16 | Email/SMTP | **Missing → wired this run** | No `EMAIL_BACKEND`/`EMAIL_*` anywhere; zero `send_mail` calls; reset/invite emails impossible. **Wired in section F** (SMTP env settings + password-reset flow). |
| 17 | Billing/entitlements | **Complete (most-tested)** | Packs/seats/feature gates enforced via `requires_entitlement` across succession/feedback/goals/AI; atomic seat ops; 12 test files. |

## TODO/stub debt
Essentially none: the only genuine stub is `HTTPLLMProvider.generate` ("not implemented in the MVP",
`apps/ai/providers.py:120`) — an unused provider option; Gemini/OpenAI/Groq are real. Everything else
flagged by the sweep is intentional-design comments or mock-only strings.

## Fix-before-deploy checklist
### P0 (blocks handover) — all addressed in this run
1. ~~Email backend + password reset~~ → **wired** (section F; commits in FINAL_REPORT.md).
2. ~~Logout doesn't revoke; MFA field mismatch~~ → **fixed** (section B).
3. ~~Visible-but-unauthorized controls (the #1 complaint)~~ → **fixed** (section D).
4. JD Generate on an inputs-less DRAFT → verified/gated in the D2/A2 pass.

### P1 (should fix — documented, not all in this run's scope)
- **Notifications beyond Slack** (in-app center) — v2 project; flagged in DEPLOYMENT_HANDOVER.md.
- Ensure the real `LLM_PROVIDER` + `GEMINI_API_KEY` are injected in the deploy env (else AI is dark-but-graceful).
- Broaden check-ins/audit test coverage.
- Refresh-token storage (localStorage → http-only cookie/BFF) + per-account login lockout (AUTH_REVIEW).

### P2 (nice)
- Implement or remove `HTTPLLMProvider`.
- Keep documenting the v1 scope cuts (career/succession/calibration/T-score/tenant-config) so they aren't
  mistaken for missing features (see docs/handoff/V1_VS_V2.md).
