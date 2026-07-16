# DEPLOYMENT_HANDOVER (PHASE2 delta) — what changed since docs/V1_REVIEW/DEPLOYMENT_HANDOVER.md

The V1 handover (`docs/V1_REVIEW/DEPLOYMENT_HANDOVER.md`) remains the base document (services,
build/start, `deploy_migrate`, monitoring, the honest not-wired list). This delta covers PHASE2 LANE 1.

## New env vars (all in `.env.example`, placeholders only)
- `LOGIN_LOCKOUT_ATTEMPTS` / `LOGIN_LOCKOUT_WINDOW_SECONDS` — account lockout (8 / 900s defaults).
- `MEDIA_ROOT` — avatar/logo uploads. **Mount a persistent volume** in production (e.g.
  `/app/media`); without one, uploads vanish on redeploy. Upgrade path: object storage (S3/GCS) via
  django-storages — a config-level change (STORAGES backend), designed not built.
- (Payments, when that lane is built: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`,
  `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` — see PAYMENTS_DESIGN.md.
  NOT read by the app today.)

## New migrations (all additive; `deploy_migrate` applies them)
identity 0004 (LoginEvent, DeviceSession) · 0005 (User profile fields + preferences) ·
0006 (Invitation) · billing 0003 (Subscription).

## New surfaces to know about
- `/api/auth/sessions*`, `/login-history`, `/my-activity`, `/profile*`, `/password-change`,
  `/email-change*`, `/mfa/disable` — all self-scoped.
- `/api/auth/invitations/<token>*` (public accept, signed 7-day tokens) +
  `/api/admin/invitations*` (HRBP+). Invitation email is best-effort; the link is always returned to
  the inviter, so onboarding works without SMTP (but configure SMTP for real tenants).
- `/api/billing/subscription` (Admin) — the INTERNAL plan/lifecycle. **No payment gateway is wired**;
  plan changes are admin-driven until the payments lane is built (human-reviewed).
- `/api/admin/org-settings` — org defaults + branding (branding gated by the Enterprise plan's
  `custom_branding`).

## Ops notes
- Lockout + throttles live in the CACHE Redis — a Redis flush clears lockout counters (fail-open by
  design; the per-IP throttle still applies).
- Device-session revocation acts at REFRESH time — a revoked session dies within the 15-min access
  lifetime (matches the blacklist model).
- Headcount: `can_add_user` enforces entitlement seats AND plan employee limits at admin-create and
  invite-accept. `seat_count=0` / `employee_limit=0` mean UNLIMITED (the provisioning default).
- Media backup: include `MEDIA_ROOT` in backups until object storage lands.
