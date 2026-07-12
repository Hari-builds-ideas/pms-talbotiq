# PHASE2 — run progress (PHASE2_BUILD.md) — **COMPLETE**

Run of 2026-07-13 (after FINAL.md, base `ce5602a`). LANE 1 built + tested + committed; LANE 2
designed only (payments + auth-rewrite deliberately NOT implemented — the human-review gate held).

## Status
### LANE 1 (built)
- [x] 1. User profile system — `a5ec063` (API: profile/photo/password-change/email-change/mfa-disable/
  my-activity + admin org-fields) + `321a06a` (My Settings page). identity 0005. 6 tests.
- [x] 2. Invitation onboarding — `b222a5c` (Invitation model 0006, signed 7-day links, public accept
  page, HRBP+ `invite_users` capability, copy-link works without SMTP, revocation wins, headcount
  enforced at accept). 5 tests.
- [x] 3. Sessions/devices/history + lockout — `57eb673` (DeviceSession + `did` claim + device-aware
  refresh, LoginEvent history, atomic per-(tenant,email) lockout, revoke/revoke-others). identity
  0004. 6 tests. No token-scheme change (the structural item went to the design lane as mandated).
- [x] 4. Subscription & plans — `1a56339` (Subscription model billing 0003, PLAN_CATALOG
  Starter/Professional/Enterprise, validated lifecycle TRIAL→…→EXPIRED with the kill switch,
  entitlement sync, 5 new plan-tier feature keys served on my-features, employee/seat headcount gate
  on create+invite, admin Subscription card). 5 tests (+1 legacy flags test updated for plan keys).
- [x] 5. Org settings + branding — `de04e49` (typed /api/admin/org-settings over TenantConfig,
  Enterprise-gated logo/color, /me `tenant_branding`, sidebar logo + `--primary` theming). 2 tests.
### LANE 2 (design only — as mandated)
- [x] D1 PAYMENTS_DESIGN.md (`be1b2e9`) · [x] D2 AUTH_REWRITE_DESIGN.md (verdict: no rewrite needed;
  cookie migration designed) · [x] D3 SECURITY_REVIEW.md · [x] D4 FUTURE_INTEGRATIONS.md ·
  [x] D5 DEPLOYMENT_HANDOVER.md (delta)
### Finish
- [x] ROADMAP.md · [x] FINAL_TESTING_CHECKLIST.md · `.env.example` extended (lockout, MEDIA_ROOT).

## Verification
- Per-feature suites green throughout (identity 57→68, billing 149→154+, administration incl. new
  org-settings + headcount tests, rbac matrix updated for `invite_users`); frontend tsc clean +
  132 vitest after every UI change; migrations additive-only and applied to the running stack.
- Full backend suite + demo_ready smoke: final run recorded in ROADMAP/commit trail.

## The line that was respected
Payments and any auth token/session rewrite were NOT implemented. They are complete, reviewable
designs with paste-ready prompts (`PAYMENTS_DESIGN.md`, `AUTH_REWRITE_DESIGN.md`) for a supervised
daylight build — money and account access don't ship unattended.
