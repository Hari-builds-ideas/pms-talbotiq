# PHASE2 ROADMAP — what was BUILT, what is DESIGNED, and the order to proceed

## BUILT this run (LANE 1 — implemented, tested, committed)
| Item | Commits | How to test |
|---|---|---|
| L1.3 Sessions/devices/login-history + account lockout | `57eb673` | Settings → Active sessions (revoke → that device can't refresh); wrong password ×8 → 429; Settings → login history. 6 backend tests (`test_sessions_lockout.py`). |
| L1.1 Profile system (photo, phone, tz/lang, prefs, change password/email, 2FA surface, activity) | `a5ec063`, `321a06a` | Topbar → My settings: edit profile, upload photo (2MB/JPEG-PNG-WebP only), change password (other sessions die), change email (confirm via link), enable/disable 2FA. Admin: PATCH `/api/admin/users/<id>/profile` for title/dept/employee-id. 6 tests (`test_profile.py`). |
| L1.2 Invitation onboarding | `b222a5c` | Users & Roles → Invite user → copy link (works without SMTP) → open `/accept-invite?...` → set password → login. Revocation beats a sent link; seats/plan limits enforced at accept. 5 tests (`test_invitations.py`). New capability `invite_users` (HRBP+). |
| L1.4 Subscription/plan model + gating + limits | `1a56339` | Entitlements → Subscription card: switch STARTER/PROFESSIONAL/ENTERPRISE → features flip instantly (server-side; my-features); EXPIRED kills gated features; employee/seat limits 409 on create+invite. 5 tests (`test_subscription.py`). |
| L1.5 Org settings + branding hooks | `de04e49` | `PATCH /api/admin/org-settings` (name/tz/lang; logo/color gated by Enterprise `custom_branding`); /me serves `tenant_branding`; the sidebar logo + `--primary` re-theme. 2 tests (`test_org_settings.py`). |

All additive migrations (identity 0004-0006, billing 0003); RBAC/HITL/tenant/audit untouched.

## DESIGNED, awaiting human review (LANE 2 — DO NOT BUILD unattended)
- **`PAYMENTS_DESIGN.md`** — Stripe + Razorpay: provider port, webhook-verified money flow into the
  L1.4 subscription state machine, invoices/refunds/retries, the never-on-frontend rules, and the
  paste-ready build prompt.
- **`AUTH_REWRITE_DESIGN.md`** — verdict: **no structural rewrite needed**; the one v2 item is the
  refresh-token → http-only cookie migration, fully designed with its prompt.
- Supporting: `SECURITY_REVIEW.md` (posture + prioritized remainder), `FUTURE_INTEGRATIONS.md`
  (seam designs), `DEPLOYMENT_HANDOVER.md` (PHASE2 delta).

## Recommended build order (after you review the designs)
1. Review PAYMENTS_DESIGN.md → build with its prompt (Stripe test-mode first) — **daylight, supervised**.
2. Review AUTH_REWRITE_DESIGN.md → build the cookie migration with its prompt — **daylight, supervised**.
3. NotificationChannel port + in-app center (FUTURE_INTEGRATIONS #1 — biggest UX gap).
4. Object storage for media; CSP headers; django-axes (SECURITY_REVIEW P2s).

## The line (why payments + auth-rewrite were NOT built)
They gate **real money and account access**. Building them unattended risks silent, high-blast-radius
mistakes (mis-verified webhooks, broken logins for every user). They are deliberately staged as
complete designs + prompts for a human-reviewed, awake build. This was the explicit contract of
PHASE2_BUILD.md and it was respected.
