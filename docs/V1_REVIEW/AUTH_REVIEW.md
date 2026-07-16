# AUTH_REVIEW — how authentication works today, and what was fixed

Grounded in code (`file:line`). Written 2026-07-13 as part of the FINAL production-handover pass.
The **Fixes applied** section at the end records what this run changed.

## 1. Login flow
`POST /api/auth/login` → `LoginView` (`apps/identity/views.py:32-54`), `AllowAny`, throttled by
`AtomicAnonThrottle`. `LoginSerializer` (`apps/identity/serializers.py:12-40`):
1. Resolves the tenant by `tenant_slug` and rejects non-active tenants (`serializers.py:25-29`).
2. Looks the user up **inside `tenant_context`** (email is unique per tenant) and checks the password
   (`serializers.py:31-36`).
3. Every failure mode (bad tenant / unknown email / wrong password / inactive) raises the **same**
   `InvalidCredentials()` 401 — good anti-enumeration posture.

If `user.mfa_enabled`, no JWTs are issued; the response is `{"mfa_required": true, "mfa_token": …}` — a
signed (`django.core.signing`), 300s, grants-nothing token (`apps/identity/mfa.py:15-24`). Step 2 is
`POST /api/auth/mfa/challenge` (`views.py:57-78`) verifying the TOTP (`django_otp` TOTPDevice) and then
minting JWTs. Otherwise JWTs are issued immediately plus a server-side session
(`establish_session`, `apps/identity/services.py:4-16`).

**OIDC** (allauth `openid_connect`, `config/settings/base.py:327-341` → `OidcCompleteView`
`views.py:166-197`) and **SAML** (per-tenant SP, `apps/identity/saml/`) exist as SSO seams.

## 2. Token mechanics (`SIMPLE_JWT`, `config/settings/base.py:298-311`)
- Access **15 min** (`JWT_ACCESS_MINUTES`), refresh **7 days** (`JWT_REFRESH_DAYS`).
- `ROTATE_REFRESH_TOKENS = True`, `BLACKLIST_AFTER_ROTATION = True`, and the
  `token_blacklist` app **is installed** (`base.py:47`).
- HS256, signing key = `SECRET_KEY`; prod re-points it at the **required** prod secret
  (`config/settings/prod.py:11-14` — fails closed without `DJANGO_SECRET_KEY`).
- Custom claims: `tenant_id`, `role`, `email` stamped on both tokens (`apps/identity/tokens.py:10-30`);
  SAML may override `role` but never `tenant_id`.

## 3. Client-side token storage
`frontend/src/lib/auth/tokenStore.ts`: **access token in memory only** (module var, `:11-19`);
**refresh token in `localStorage`** (`pms.refresh`, `:9,20-34`) — the file itself flags the
http-only-cookie/BFF alternative (`:4-6`). Axios (`shared/src/api/client.ts`): request interceptor
attaches the Bearer (`:54-60`); on 401 it refreshes **once** (guarded `_retried`) via a **single-flight**
shared promise (`:66,106-108`) and retries; refresh failure → `tokenStore.clear()` + forced logout event
→ `AuthContext` drops to unauthenticated and clears the query cache (`AuthContext.tsx:62-71`).
Refresh endpoint is the stock `TokenRefreshView` (rotation on → each refresh blacklists the old token).

## 4. Logout
`POST /api/auth/logout` → `LogoutView` (`views.py:122-138`) blacklists the refresh token and flushes the
session — the server side is correct. **BUG (P0, fixed this run):** the client called it with an
**empty body** (`shared/src/api/endpoints.ts:109` — `api.post("/auth/logout", {})`) while
`LogoutSerializer` **requires** `refresh` (`serializers.py:72-73`) → 400 **before any blacklist**, and
`AuthContext.logout()` swallowed the error. Net effect: logout was client-only; the refresh token stayed
valid for up to 7 days. See **Fixes applied**.

## 5. Session handling
Django sessions exist for the SSO/allauth path (cache-backed, dedicated Redis DB `/2`,
`base.py:226-236`). Prod cookies: `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE = True`, HSTS, SSL
redirect, nosniff, `X_FRAME_OPTIONS=DENY` (`prod.py:20-28`). `SESSION_COOKIE_HTTPONLY`/`SAMESITE` relied
on Django defaults (HttpOnly True / Lax) — now pinned explicitly (see Fixes). **CSRF posture is
coherent:** DRF uses **only** `JWTAuthentication` (`base.py:273-275`, no SessionAuthentication), so the
Bearer API is stateless and CSRF-exempt by design; `CsrfViewMiddleware` still protects the allauth/SAML
session flows; `CSRF_TRUSTED_ORIGINS` is env-driven in prod.

## 6. Authorization resolution per request
1. `TenantMiddleware` (`apps/tenancy/middleware.py:25-60`) validates the Bearer and binds the tenant
   from the **signed claims only** (never headers/body), reset in `finally`.
2. DRF `JWTAuthentication` → `request.user`.
3. `RBACMixin` (`apps/rbac/mixins.py:49-60`) → `IsAuthenticated` + `HasCapability`
   (+ `WithinScope` for object scope).
4. `HasCapability` fails closed — **no `required_capability` declared → deny**
   (`apps/rbac/permissions.py:68-75`).
5. Row scope via `actor_can_access` (OWN / TEAM / TENANT).

## 7. Security concerns found (pre-fix)
- **P0 — logout didn't revoke** (empty body vs required `refresh`; above). **FIXED.**
- **P0 — real MFA was non-functional** — field-name mismatch: server issues/expects `mfa_token`
  (`views.py:50`, `serializers.py:47`) but the client read `res.challenge` and posted
  `{challenge, code}` (`LoginPage.tsx:57-58`, `endpoints.ts:102-103`, `types.ts:94-98`); the MSW mock
  also returned `challenge`, so tests passed while production MFA would 400. Sibling: `mfaEnroll`
  expected `otpauth_url` but the server returns `config_url` (`endpoints.ts:105` / `views.py:90`).
  **FIXED** (client aligned to the server contract; mocks updated to the real shape).
- **P1 — refresh token in `localStorage`** → XSS-exfiltratable; combined with 7-day lifetime this is the
  weakest point. Mitigations in place: access-in-memory, rotation+blacklist, forced-logout wiring; the
  full fix (http-only cookie / BFF) is a deliberate v2 item — see verdict.
- **P1 — no per-account lockout** — only the IP throttle (`100/min` anon). Distributed credential
  stuffing is not stopped; MFA-code guessing shares the same bucket. Deferred with a recommendation
  (django-axes or an account-scoped counter) — see verdict.
- **No working password reset / no email backend** — no reset endpoints existed, no `EMAIL_*` settings
  anywhere (Django silently fell back to `localhost:25`). **FIXED in section F** of this run: SMTP
  settings wired from env + a standard tenant-scoped reset flow (request + confirm) + frontend link.
- Positives: Argon2 first hasher (`base.py:252-257`), uniform 401s, prod fail-closed secrets, blacklist
  app installed, atomic anon throttle, `ACCOUNT_EMAIL_VERIFICATION="none"` is a deliberate SSO-trust
  choice (noted).

## Verdict
**Architecture: sound** (signed-claim tenant binding, fail-closed RBAC, rotation+blacklist, Argon2).
**Was NOT production-ready** because of three auth-critical defects — logout non-revoking, MFA broken
against the real API, no password reset/email. After this run's fixes (logout revocation, MFA contract,
email + reset flow, pinned session-cookie flags), the remaining **accepted risks for v1** are:
refresh-in-localStorage (P1 — move to an http-only cookie/BFF in v2, or shorten `JWT_REFRESH_DAYS`) and
no per-account lockout (P1 — add django-axes or an account counter). Both are documented in
`OPEN_QUESTIONS.md` for the deployment decision.

## Fixes applied (this run)
See FINAL_REPORT.md for commit hashes.
1. **Logout revocation** — client now sends `{refresh: tokenStore.getRefresh()}`; `AuthContext.logout`
   captures the token **before** clearing storage. Verified: server blacklists on logout.
2. **MFA contract fix** — `mfa_token` (login response + challenge request) and `config_url` (enroll)
   aligned across `shared/src/types.ts`, `shared/src/api/endpoints.ts`, `LoginPage.tsx`, and the MSW
   mocks now mirror the REAL backend shape so tests exercise the true contract.
3. **Session-cookie pinning** — `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SAMESITE = "Lax"`
   set explicitly in prod settings.
4. **Email + password reset** — wired under section F (EMAIL_* env settings, tenant-scoped
   request/confirm endpoints using Django's `PasswordResetTokenGenerator`, no-enumeration responses,
   frontend "Forgot password?" flow).
