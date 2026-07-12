# QA_CHECKLIST — production QA record (verified 2026-07-13)

**How verified:** containers recreated on final code + rich reseed (`demo_ready.sh`), then three layers:
(1) the **57/57 E2E smoke** over real HTTP (six-step journey per role + agent plan→approve + injection
refusal), (2) **9/9 targeted live probes** for this run's fixes (below), (3) the automated suites
(backend full-suite green; frontend 132 vitest + tsc). ✅ = verified pass against the running app;
◻ = code-verified only (needs a human click-through; listed in FINAL_REPORT's human checklist).

## This run's fixes — live-verified (9/9 probes)
- ✅ `/me` returns server-computed `capabilities` (Employee 20, Manager 39); Employee lacks
  `approve_review`, Manager has it (D).
- ✅ Chat read path resolves a NAMED person ("how is Vera doing on her goals?" → Vera, not the caller) (C).
- ✅ Pronoun follow-up + count route ("how many reviews does she have?" → "Vera Lindqvist has 1
  review(s), 1 open") — live on Gemini (C).
- ✅ Chat memory never widens scope (Employee asking about Vera → "No data in your scope") (C).
- ✅ Password-reset request → 200 even for unknown email/tenant (no enumeration); confirm with a bad
  link → generic 400 (F). Full flow (email link → new password logs in, old rejected, sessions revoked)
  covered by 4 backend tests on the locmem mail backend.
- ✅ Logout blacklists the refresh token (logout 205 → refresh replay 401) (B).
- ✅ Defense in depth intact: an Employee POSTing approve on a review still 403s server-side (D).

## Per module (CRUD · edge cases · errors · loading · empty · roles)
| Module | Verified | Notes |
|---|---|---|
| Login/MFA/logout | ✅ login per 4 roles (smoke); logout revocation (probe); MFA contract fixed — ◻ needs one human TOTP enroll+challenge (no seeded MFA user) |
| Password reset | ✅ endpoints + 4 backend tests; ◻ human: click "Forgot password?" → email link → new password |
| Dashboards ×4 roles | ✅ smoke hits every role's cockpit sources; tiles have loading/empty states (code-verified) |
| Goals & OKRs | ✅ smoke (list/create/approve/actuals per role) + 111 goals/query-budget tests; picker scope fixed |
| Reviews | ✅ smoke (list per role, AI draft flow); ActionBar now capability-gated (4 unit tests); ◻ human: employee sees a clean read-only review page |
| Check-ins | ✅ smoke (own + team + respond) |
| Feedback/360 | ✅ smoke (cycles, give, mine, summaries release gate); create-cycle picker scope fixed |
| Recognition | ✅ smoke (feed + post) |
| Employees/Org | ✅ smoke (tree/search/vacancies/positions) |
| JD library | ✅ smoke (library per role); known trap: Generate on an inputs-less DRAFT 422s by design — ◻ human: confirm the UI path fills inputs first |
| Analytics | ✅ smoke (individual/department/calibration-hidden); pickers scope fixed |
| Chat/agent | ✅ smoke (plan→approve, session memory, isolation, injection) + memory probes above |
| Approvals | ✅ smoke (inbox/workflows; step decisions assignee-checked) |
| Admin (users/entitlements) | ✅ smoke (admin lists); mutations covered by backend tests |
| Audit | ✅ smoke (HRBP console; append-only enforced by model tests) |
| Notifications | ⚠ no in-app system (Slack-only, silent no-op without webhook) — known gap, documented in PROJECT_ASSESSMENT + handover |
| Email sending | ✅ reset mail via locmem in tests; ◻ production SMTP is deploy-time config (EMAIL_*) |

## Role variations spot-checks
- Employee: own-scope everywhere (smoke §employee rows all 200/403-as-expected); no manager tiles; no
  action buttons on reviews (unit-tested); chat scope-refuses others' data (probe).
- Manager: subtree scope (create goal/review/cycle pickers now offer exactly the subtree); approve flows.
- HRBP: tenant reads, calibration/summaries release, no admin pages.
- Admin: users/entitlements; no bypass of tenant isolation (matrix: NOBODY).

## Residual human checklist
Consolidated in `FINAL_REPORT.md` §Human testing (the ◻ items above).
