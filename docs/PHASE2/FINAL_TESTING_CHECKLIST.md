# PHASE2 FINAL_TESTING_CHECKLIST — verify LANE 1 end to end (per role)

Stack: recreate web+worker (migrations apply via compose run or deploy_migrate), reseed if desired.
Accounts: `admin@acme.test` / `priya@acme.test` (HRBP) / `ada@acme.test` (Mgr) / `akhil@acme.test`
(Emp), password `Passw0rd!demo`, at :8090.

## As ANY role (start with akhil — Employee)
1. **Profile:** Topbar avatar → My settings. Edit name/phone/timezone → Save → reload → persisted.
2. **Photo:** Upload a PNG/JPEG < 2MB → avatar appears. Try a .txt renamed .png → rejected.
3. **Preferences:** toggle notification channels → Save → reload → kept.
4. **Change password:** wrong current → error; correct → success toast "other sessions signed out";
   log in elsewhere first and confirm that session can't refresh afterwards.
5. **Change email:** enter a new address + password → confirmation link arrives (or web container log
   with the console backend) → open it (lands on /settings) → email updated; old email can't log in.
6. **2FA:** Enable → add secret to an authenticator → confirm code → badge "Enabled". Log out/in →
   TOTP challenge works (REAL contract). Disable with password.
7. **Sessions:** log in from a second browser → both listed; Revoke the other → it's signed out at
   its next refresh (≤15 min); "Sign out others" keeps only this device.
8. **Login history:** shows your sign-ins; make 2 failed logins first and see LOGIN_FAILED rows.
9. **Lockout:** 8 wrong passwords in a row → "Too many login attempts" (429), even with the RIGHT
   password; wait 15 min (or reduce `LOGIN_LOCKOUT_ATTEMPTS` locally) → works again.

## As HRBP (priya) — invitations
10. Users & Roles → **Invite user** (any email, role Employee) → copy the link (no SMTP needed) →
    open it in a private window → set a password → account created in ACME with that role → login.
11. Invite again → revoke from the pending list → the copied link now shows "invalid/expired/revoked".
12. As akhil, confirm `/api/admin/invitations` is forbidden (no UI entry point exists for Employee).

## As Admin (admin@) — subscription, limits, org settings
13. Entitlements → **Subscription** card: switch to ENTERPRISE → (as any user, reload) AI features +
    advanced-analytics/custom-branding flags on immediately; switch back to STARTER → premium off.
14. Set status PAST_DUE → features stay; EXPIRED → every gated feature off; ACTIVE → restored.
15. Seats: set seats to the current user count → Create user AND invite-accept both 409 ("no seats");
    raise seats → works.
16. **Org settings** (`PATCH /api/admin/org-settings` or via API client): set name/timezone; on
    STARTER, logo/color → 403 (Enterprise feature); on ENTERPRISE set `logo_url` + `#RRGGBB` color →
    every user's sidebar shows the logo and the primary color re-themes after reload.

## Regression sweep
17. `docker compose run --rm web pytest -q` → green. `cd frontend && npx tsc --noEmit && npm test` →
    green. `BASE=http://localhost:8090 ./scripts/demo_ready.sh` → 57/57 DEMO READY.
18. Spot-check v1 behavior unchanged: goals %+bars, reviews gating (employee sees read-only),
    chat copilot resize/persist + memory.
