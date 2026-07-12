# AUTH_REWRITE_DESIGN — verdict: **no structural rewrite needed for v1/v2-scale**

Reviewed after the FINAL.md auth fixes + the PHASE2 LANE-1 additions. Grounded in
`docs/V1_REVIEW/AUTH_REVIEW.md` and the current code.

## What the additive work already delivered (no rewrite)
- Logout revokes (blacklist) · password reset AND change revoke every outstanding refresh token +
  device session · real MFA works (contract fixed) · **device sessions** (`did` claim, list/revoke,
  revoked sessions can't rotate — enforced at refresh) · **login history** · **account lockout**
  (atomic per-(tenant,email) window) · session-cookie flags pinned · anti-enumeration everywhere.
- These cover LANE-1 item 3 fully. The token SCHEME (simplejwt, 15-min access in memory, 7-day
  rotating+blacklisted refresh, tenant/role claims) is untouched and sound.

## The one structural item that remains (v2, human-reviewed) — refresh-token storage
**Problem:** the refresh token lives in `localStorage["pms.refresh"]` → XSS-exfiltratable. Everything
else is mitigation (rotation, blacklist, revocation, short access life).
**Design (when chosen):** move the refresh token to an **http-only, Secure, SameSite=Strict cookie**
scoped to `/api/auth/token/refresh`:
1. Login/MFA/accept-invite responses SET the cookie (server-side) and stop returning `refresh` in the
   body; access token stays in the JSON (memory-only client-side).
2. `/api/auth/token/refresh` reads the cookie (body fallback during migration), rotates, RE-SETS the
   cookie. CSRF: a rotating double-submit token or `SameSite=Strict` + custom header requirement.
3. Logout clears the cookie + blacklists. Mobile keeps body-token flow via a client-type flag
   (SecureStore is already safe storage there).
4. Roll out dual-mode (cookie preferred, body fallback) → remove fallback after mobile ships.
**Effort:** ~2-3 days incl. tests. **Risk:** login/refresh regressions — why it's design-only here.

### Ready-to-paste implementation prompt
```
Read docs/PHASE2/AUTH_REWRITE_DESIGN.md. Implement the http-only refresh-cookie migration EXACTLY:
dual-mode first (cookie preferred, body fallback), SameSite=Strict + Secure + path-scoped cookie,
rotation re-sets the cookie, logout clears it, mobile keeps the body flow via X-Client header.
Update shared/src/api/client.ts to stop persisting the refresh token when the cookie mode is active.
Keep every existing auth test green and add: cookie set on login, refresh works with no body token,
XSS-simulated localStorage read finds nothing, logout clears cookie + blacklists. Never weaken
rotation/blacklist/lockout/device-session enforcement. Commit per step.
```

*Also listed for v2 (non-structural, do anytime): shorten `JWT_REFRESH_DAYS`, add django-axes if a
stronger lockout is wanted, per-tenant SSO-enforcement toggles.*
