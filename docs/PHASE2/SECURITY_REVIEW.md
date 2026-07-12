# SECURITY_REVIEW — enterprise posture, grounded in code (post-FINAL + PHASE2 LANE 1)

Current state per area + the prioritized remainder. Trivially-safe items were FIXED in LANE 1;
structural ones carry a prompt-pointer.

| Area | State | Evidence |
|---|---|---|
| Password hashing | ✅ Argon2 first hasher; validators enforced on set/change/reset/invite | `base.py` PASSWORD_HASHERS/VALIDATORS |
| Secrets | ✅ env-only; prod fails closed w/o SECRET_KEY; no secrets in repo (scan clean); Flower basic-auth documented | `prod.py:11`, `.env.example` |
| JWT | ✅ 15-min access (memory), 7-day rotating+blacklisted refresh, tenant/role claims, device-session (`did`) revocation at refresh, revoke-on-logout/reset/change | `tokens.py`, `security.py`, AUTH_REVIEW |
| Token storage | ⚠ refresh in localStorage — ACCEPTED v1 risk w/ mitigations; the http-only-cookie migration is designed (AUTH_REWRITE_DESIGN.md) | tokenStore.ts |
| Cookies | ✅ Secure/HttpOnly/SameSite pinned in prod (session + CSRF) | `prod.py:22-26` |
| CSRF | ✅ coherent split: Bearer API is stateless (no SessionAuthentication); CsrfViewMiddleware guards allauth/SAML session flows | `base.py` REST_FRAMEWORK |
| XSS | ✅ React auto-escaping; no dangerouslySetInnerHTML in product code; CSP is a deploy-layer add (handover note) | grep clean |
| SQLi | ✅ ORM-only; no raw SQL in product paths; strict SQL mode on | `base.py` DATABASES OPTIONS |
| Rate limiting | ✅ per-IP anon throttle + entitlement-driven tenant/user/AI throttles (atomic Redis) + **account lockout (L1.3)** + MFA on same anon bucket | `throttling.py`, `security.py` |
| API protection | ✅ fail-closed RBAC (`HasCapability` denies w/o declared capability), object scope, tenant fail-closed managers, capability list served to UI from the same matrix | `permissions.py`, `matrix.py` |
| Audit | ✅ append-only at model+manager level; all consequential writes audited incl. new auth/profile/subscription events | `apps/audit` |
| PII | ✅ AI gateway scrubs prompts; Sentry send_default_pii=False + header scrub; 360 anonymization min-volume + leak scan | `gateway.py`, `observability.py` |
| Secure uploads | ✅ (L1.1) magic-byte sniffing (JPEG/PNG/WebP), 2MB cap, random tenant-prefixed names, served ONLY via authenticated scope-checked endpoints — never static | `profile_views.py` |
| Session mgmt | ✅ (L1.3) device sessions list/revoke/revoke-others, login history, lockout | `security.py` |
| Enumeration | ✅ uniform 401 login; always-200 reset; generic-400 confirm; 404 sessions/invites; lockout keyed on attempted email regardless of existence | identity views |
| Backup / DR | ⚠ deploy-layer: managed-MySQL PITR + tested restore required (handover §1); Redis is rebuildable state except the broker queue (accept or use a durable broker later) | DEPLOYMENT_HANDOVER |
| Encryption at rest | ⚠ deploy-layer: enable disk/volume encryption on managed DB + storage; `DB_SSL_CA` wired for TLS in transit | `base.py` DATABASES |

## Prioritized remainder
1. **P1 (designed)** — refresh-token cookie migration (AUTH_REWRITE_DESIGN.md prompt).
2. **P1 (deploy)** — CSP + security headers at the LB/nginx; managed-DB encryption + tested restores.
3. **P2** — django-axes (or extend the lockout with progressive backoff); shorten `JWT_REFRESH_DAYS`;
   object storage for media (design note in D5); dependency scanning (pip-audit/npm audit) in CI.
4. **P2 (product)** — self-approval block decision; per-tenant LLM keys (data governance).
