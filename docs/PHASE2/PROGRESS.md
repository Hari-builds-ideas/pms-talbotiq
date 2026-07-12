# PHASE2 — run progress (PHASE2_BUILD.md)

Run started 2026-07-13 (continuing the FINAL.md run, base `ce5602a`). LANE 1 = BUILD (tested,
committed); LANE 2 = DESIGN-ONLY (payments + any auth rewrite are NOT implemented — human-review gate).

## Status
### LANE 1 (build)
- [ ] 1. Complete user profile system (model + API + UI + tests)
- [ ] 2. Invitation-based onboarding (invite → set password → join tenant w/ role)
- [ ] 3. Sessions/devices/login-history + account lockout (additive only)
- [ ] 4. Subscription & plan model on existing entitlements (no gateway) + gating UI
- [ ] 5. Org settings + branding hooks
### LANE 2 (design only)
- [ ] D1 PAYMENTS_DESIGN.md · [ ] D2 AUTH_REWRITE_DESIGN.md · [ ] D3 SECURITY_REVIEW.md ·
  [ ] D4 FUTURE_INTEGRATIONS.md · [ ] D5 DEPLOYMENT_HANDOVER.md
### Finish
- [ ] ROADMAP.md · [ ] FINAL_TESTING_CHECKLIST.md

## Log
- FINAL.md completed first (see docs/V1_REVIEW/FINAL_REPORT.md; commits d7e20bb…ce5602a).
- Recon of existing surfaces (User model, billing/entitlements, tenant config, token/session infra,
  throttles, uploads, frontend settings mount points, migration numbering) launched.
- Planned build order (dependency-driven): 3 (sessions/lockout/history — the security data layer) →
  1 (profiles, consumes 3's surfaces) → 2 (invites) → 4 (plans/subscriptions) → 5 (org settings).
