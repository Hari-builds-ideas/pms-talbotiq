# VERIFY_PHASE2 — Phase-2 account features, verified end-to-end

**Date:** 2026-07-13 · **Verified by:** live HTTP probes against the running stack
(`http://localhost:8090` → nginx → Django), never the test client. Probe run:
**49/49 checks passed** (scratchpad `phase2_verify.py`). Every destructive account
op ran on a throwaway user created through the invite flow — demo accounts untouched.

Also in this run (job 1): the **"Open the draft to review it" bug is fixed and
live-verified** — details at the bottom.

---

## Scoreboard

| # | Feature group | Verdict | Checks |
|---|---------------|---------|--------|
| 1 | Profile system (edit, password change, email change, 2FA surface) | **PASS** | 16/16 |
| 2 | Password reset / forgot password | **PASS** | 6/6 |
| 3 | Invitation onboarding **+ resend** | **PASS** | 10/10 |
| 4 | Sessions, revoke, login history, lockout | **PASS** | 6/6 |
| 5 | Subscription / plan model + feature gating | **PASS** | 9/9 |

## What was fixed during verification

1. **RESEND invite did not exist — built it.** `POST /api/admin/invitations/<id>/resend`
   (INVITE_USERS = HRBP+): re-signs a **fresh 7-day link** (the signature timestamp is the
   expiry clock), re-sends the email (best-effort; link always returned), audits
   `admin.invitation_resent`. Only PENDING invites can be resent — ACCEPTED/REVOKED → 409,
   so a dead invite can never be revived. UI: **Resend** button next to Revoke in the
   Invite dialog (Admin → Users); the fresh link appears in the copy-paste box.
   Commit `df4975a` (+ test `test_resend_reissues_a_working_link_and_is_pending_only`).
2. **ACME demo tenant was on STARTER (25-employee cap) with 211 people** — every live
   invite-accept 409'd ("upgrade the plan"). The gate was working; the demo data was wrong.
   Seed now puts ACME on **ENTERPRISE** (unlimited, same STARTER+FULL_AI packs). Commit `b372bbd`.
3. Nothing else needed fixing — groups 1, 2, 4 and 5 passed as built.

---

## 1 · Profile system — PASS

- `GET /api/auth/profile` returns the caller's profile; `PATCH` persists
  `display_name / phone / timezone / language / preferences`.
- Invalid timezone → 400. **email/role are not self-editable** (silently ignored — org-controlled).
- `GET /api/auth/my-activity` (self audit trail) works.
- **Password change** (`POST /api/auth/password-change`, requires `current_password`):
  old password dead, **every session/refresh token revoked**, new password logs in.
- **Email change**: `POST /api/auth/email-change` {new_email, current_password} → signed
  1-hour confirm link emailed to the NEW address → `POST /api/auth/email-change/confirm`
  → login works on the new email only.
- **2FA surface**: `POST /api/auth/mfa/enroll` returns the TOTP provisioning secret;
  `mfa/disable` is password-confirmed. (Full TOTP login challenge was verified in the
  FINAL run's real-MFA contract tests.)

## 2 · Password reset — PASS

- `POST /api/auth/password-reset` {tenant_slug, email} → always `{"ok": true}`
  (unknown email = identical response, **no user enumeration**).
- Email carries `/reset-password?tenant=…&uid=…&token=…`; confirm
  (`POST /api/auth/password-reset/confirm` {tenant_slug, uid, token, new_password})
  sets the password and revokes all sessions. **Token is single-use** (second confirm → 400).
- Login with the reset password verified.
- Dev email = console backend (token scraped from web logs); production uses the
  `EMAIL_*` SMTP vars from `.env.example`.

## 3 · Invitation onboarding + RESEND — PASS (resend built this run)

- HRBP creates invite → 201 with `invite_url` (works without SMTP); Employee → 403.
- **Resend** returns a fresh URL (new 7-day window); Employee resend → 403.
- Public detail on the resent link shows email/tenant/role; accept creates the user
  **in the invite's tenant with the invited role**, then the link is dead (single-use).
- Accepted invite can't be resent (409). Invited user logs in immediately.
- Seats + plan employee-limit enforced **at accept time** (the 409 that exposed fix #2).

## 4 · Sessions, history, lockout — PASS

- `GET /api/auth/sessions` lists device sessions (two logins → two rows).
- `POST /api/auth/sessions/revoke-others` → the other session's **refresh token is dead
  (401)** — enforced by the `did` claim check at refresh, not just UI. Current session keeps working.
- `GET /api/auth/login-history` shows the events (success/failed/lockout kinds).
- **Lockout**: 8 wrong passwords in 15 min → even the **correct** password gets 429
  (same response either way — no oracle). Window resets on success/expiry.

## 5 · Subscription / plans + feature gating — PASS

- `GET/PATCH /api/billing/subscription` (Admin only — Employee → 403): plan, status,
  features, limits, full catalog (STARTER / PROFESSIONAL / ENTERPRISE).
- **Server-side gating flips instantly** (tenant cache invalidated on `set_plan`):
  - STARTER → `custom_branding` false on `/api/billing/my-features`, branding PATCH on
    `/api/admin/org-settings` → **403**.
  - ENTERPRISE → flag true, same PATCH → 200.
- **UI hides/locks accordingly** — `hasFeature()` (fed by `/billing/my-features`, the
  same flags the server enforces) gates the chat panel, career roadmap, agent tiles
  (`ChatPanel.tsx`, `CareerPage.tsx`, `cockpit-roles.tsx`, `managerDashboard.tsx`);
  Billing shows Unlocked/Lock badges per feature. Server remains the real gate.
- Headcount: plan `employee_limit` + entitlement seats enforced on user-create and
  invite-accept (0 = unlimited).

---

## Job 1 — the "Open the draft to review it" bug (FIXED + live-verified)

**Root cause (two layers):**
- The completion chip on a finished plan (§E suggestion "Open the draft to review it")
  only **prefilled the chat input** — clicking it sent the button text as a message.
- The agent then misrouted that text ("review" → performance intent) and answered
  with a **goals list**.

**Fix (commit `9fecbe4`):**
- **Frontend:** when the completed step has a result artifact with a deeplink, the
  suggestion chip **navigates** to it (e.g. `/reviews/<id>`); the prefill behavior
  remains only for suggestions with nothing to open.
- **Backend (defense in depth):** a definite-reference "open the/that/it…" message is
  intercepted **before LLM classification**, resolves the session's grounded reference
  (access re-checked), and returns `intent: "navigate"` + `deeplink` — the chat bubble
  renders an **Open** button. With nothing to resolve it answers honestly ("I don't see
  a recent record like that…") — **never a goals dump**. "Open **a** check-in" (new-thing
  ask) is deliberately not intercepted.
- 3 new tests in `apps/ai/tests/test_chat_memory.py`.

**Live proof (real Gemini, real HTTP):** "make a review for Vera" → plan → approve
`draft_review` → artifact `/reviews/6a12934a…` → send the exact button text →
`intent=navigate`, deeplink **matches the artifact**, answer = "Here it is — opening review."

## Demo-data cleanup (also this run)

- Seed now **deletes** non-spec DRAFT junk goals ("BUG1 repro goal" etc.) on reseed —
  commit `89a128d`. Post-reseed goals API: junk **NONE**, KPI progress spread 26–100%.
- **Goals screen scoped to the working cycle** — the 45 archived prior-cycle goals
  (kept on purpose for analytics trends) no longer render as duplicates — commit `cd88dca`.
- Probe leftovers cleaned: stray invites revoked, probe users deactivated.

## Commits in this run

| Commit | What |
|--------|------|
| `9fecbe4` | fix(chat): Open-the-draft navigates (deeplink) instead of pasting into chat |
| `89a128d` | chore(seed): reseed deletes non-spec DRAFT junk goals (BUG1 leftovers) |
| `cd88dca` | fix(goals): scope goals screen to working cycle, hide archived history |
| `df4975a` | feat(identity): resend invitation — fresh 7-day link + email + UI |
| `b372bbd` | fix(seed): ACME demo tenant on ENTERPRISE plan (invite demo works) |

**Green:** backend full suite **1477 passed**, frontend `tsc` clean + vitest **132 passed**,
demo_ready smoke **57/57**.
RBAC / HITL / tenant isolation / audit log untouched — every new surface re-checks
capability server-side and writes audit records.
