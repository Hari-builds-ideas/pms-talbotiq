# PROD_E_HANDOVER.md — package for the testing team + deployment team

**Goal:** produce everything the security/vuln testing team and the deployment team need, so they can
proceed with minimal clarification. Grounded in the real code.

## 1. Update `.env.example` (production-grade, this PMS only)
- Add every NEW variable introduced by PROD_A–D: `APP_NAME`; Google OAuth (`GOOGLE_OAUTH_CLIENT_ID`,
  `GOOGLE_OAUTH_CLIENT_SECRET`); payments (`PAYMENTS_ENABLED`, `STRIPE_SECRET_KEY`,
  `STRIPE_WEBHOOK_SECRET`, `STRIPE_PUBLISHABLE_KEY`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`,
  `RAZORPAY_WEBHOOK_SECRET`); plus anything else added. Each with a one-line comment; placeholders only;
  mark clearly which are TEST-MODE vs go-live. Keep it verified against config/settings/prod.py.

## 2. `docs/SECURITY_TESTING_HANDOVER.md` (for the testing team)
- The role/tenant model + how to test it (the 4 roles, tenant acme, the accounts, `Passw0rd!demo`).
- Point them at the one-command automated suite (`scripts/qa_handover.sh`) and the manual checklist.
- The surfaces most worth security/vuln attention: auth (login, reset, MFA, sessions, Google/SSO,
  self-serve signup), RBAC boundaries, tenant isolation, the payment webhooks (signature verification),
  file upload (profile photo), and the AI endpoints. Note what's already tested (injection matrix,
  cross-tenant, RBAC) so they extend rather than repeat.
- The honest STAGED/known list: payments are TEST-MODE (live keys pending), Google/SSO need the human's
  real OAuth creds, mobile deferred to v2.

## 3. `docs/DEPLOYMENT_HANDOVER.md` (for the deployment team — refresh it)
- Required services (web/gunicorn, celery worker, celery beat, MySQL, Redis broker+cache), the prod
  compose, build + startup, `deploy_migrate`, seeding, TLS/LB, health checks, monitoring (/metrics +
  Sentry), MEDIA storage for uploads, and email/SMTP.
- The go-live steps for the staged items: add live Stripe/Razorpay keys + register live webhook URLs +
  set PAYMENTS_ENABLED=true; add Google OAuth creds; provision managed Redis + worker autoscaling for
  scale (per PROD_D report).
- Placeholders only, no secrets.

## 4. Final report
Write `docs/PROD_READY_REPORT.md`:
- What changed per file (A–E), with commits.
- The human's morning to-do: drop in real logo/favicon/name assets; add Google OAuth creds + test
  Sign-in-with-Google; run payments in test mode with test cards to confirm; review the AI scale report.
- The exact morning testing checklist (per role: signup a new org, import employees, sign in with Google
  in test, upgrade a plan through test-mode checkout, confirm AI degrades gracefully).
- Any QUESTIONS / product decisions left for the human.
- A clear "what is production-ready vs what still needs the human/infra" summary.

## Done when
- `.env.example` covers all new vars (placeholders); the two handover docs + the final report exist and
  are code-grounded and honest; tests green. Logged in PROD_PROGRESS.md. Then STOP — the run is complete.
