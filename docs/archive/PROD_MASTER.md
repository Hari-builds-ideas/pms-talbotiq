# PROD_MASTER.md — unattended production-readiness session

Take the PMS from "functionally complete" to "ready to hand the testing team for security/vuln testing,
then the deployment team." Work **fully autonomously** through every file below, in order. Do NOT stop to
ask questions. Make the change, keep tests green, commit per change, and only stop at the very end with
`docs/PROD_READY_REPORT.md` + a testing checklist the human walks in the morning.

If something is genuinely ambiguous, make the simplest correct choice for a real multi-tenant SaaS,
write it in a QUESTIONS section, and keep going — never block. If context runs low, finish the current
file cleanly, write a precise "resume here" note in `docs/PROD_PROGRESS.md`, and stop; the run resumes by
pointing /goal at this file again.

## Iron rules (never break)
- Never break a working feature. Real data only; honest empty states.
- Never weaken RBAC, HITL, tenant isolation, or the audit log — every new surface enforces them.
- Keep backend AND frontend tests green after every change; add tests for every new feature; commit per
  change.
- Additive, reversible DB migrations only (nullable/defaulted); never destructive.
- Never commit secrets. Payments build against **TEST-MODE keys only** via env placeholders; never live
  keys, never a real charge. All new secrets get placeholders in `.env.example`.
- Never log into the human's external accounts. Where a real account/key is needed (Stripe, Google OAuth),
  build + document the exact step the human does; do not attempt it.

## Build files — do them IN THIS ORDER
1. `PROD_A_BRANDING.md` — favicon, logo, app name, profile photos. (Human will drop in real images; use
   the seam so they swap easily.)
2. `PROD_B_ONBOARDING_SSO.md` — how a NEW organization signs up and starts using the product at scale:
   self-serve tenant signup, first-admin creation, employee onboarding (bulk + invite), and Sign-in with
   Google / SSO (OIDC/SAML). This is the "how does a real customer start using it" answer.
3. `PROD_C_PAYMENTS.md` — real subscription + payments pipeline (Stripe + Razorpay) in TEST MODE: plan
   changes and seat adds require payment before the entitlement activates; webhooks; invoices. Built and
   verified against test keys.
4. `PROD_D_AI_ROBUSTNESS.md` — make the AI production-safe under real load (fix PROVIDER_ERROR, right
   model, retry/backoff, graceful degrade, concurrency check).
5. `PROD_E_HANDOVER.md` — the package for the testing team (security/vuln testing) and the deployment
   team: updated `.env.example`, deploy docs, what to test, known-staged items.

## Final output
- Update `docs/PROD_PROGRESS.md` after each file.
- End with `docs/PROD_READY_REPORT.md`: what changed per file, what the human must do (drop real images,
  add live Stripe/Google keys later), the exact morning testing checklist, and any QUESTIONS.
- Do all of it. Only stop at the end (or at a clean documented resume point).
