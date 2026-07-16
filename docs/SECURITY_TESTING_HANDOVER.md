# SECURITY_TESTING_HANDOVER — for the security/vuln testing team

The PMS ("Axiom") is a multi-tenant Django + DRF backend + React SPA. This is the
map of what to test, what's already covered (extend, don't repeat), and how to run.

## 1. Role / tenant model + how to test it

- **Four roles**, increasing data scope: `EMPLOYEE` (own) < `MANAGER` (own + team)
  < `HRBP` (business-unit) < `ADMIN` (whole tenant). RBAC is enforced **server-side
  on every endpoint** (`apps/rbac`, capability matrix) — the SPA never gates.
- **Tenant is the isolation boundary.** Every domain model is `TenantScopedModel`
  with a fail-closed manager; JWTs embed `tenant_id` + `role`; a cross-tenant id is
  a 404, not a leak.
- **Test tenant `acme`**, password **`Passw0rd!demo`**, accounts:
  `admin@` / `priya@` (HRBP) / `ada@` (Manager, MFA) / `akhil@` (Employee) `@acme.test`.
  A second tenant `globex` (`gadmin@/gmgr@/gemp@globex.test`) exists for
  cross-tenant probes.

## 2. Run the automated suite first (then extend)

- **One command:** `./scripts/qa_handover.sh` — reseeds, seeds the cross-tenant
  fixture, and runs `scripts/qa_verify.py` (every module × 4 roles, negatives,
  cross-tenant, account features, data hygiene). `QA_SKIP_AI=1` to skip live-model
  checks.
- **Backend unit/integration:** `docker compose exec web pytest` (≈1500 tests).
- **Manual/visual:** `docs/HARI_MANUAL_TEST.md`.

## 3. Surfaces most worth security/vuln attention

- **Auth**: login, password reset (no enumeration), MFA (TOTP, anti-replay),
  device sessions/lockout, **self-serve signup** (`POST /api/auth/signup`, public,
  IP-throttled), Google/SSO (OIDC no-JIT), SAML (signed assertions, replay-protected).
- **RBAC boundaries**: attempt each capability as each role; the **role ceiling** on
  invites *and* CSV import (an HRBP must not mint an ADMIN).
- **Tenant isolation**: signup creates a fresh isolated tenant; **CSV import** must
  never link a manager across tenants; **payment webhooks** for tenant A must never
  touch tenant B.
- **Payment webhooks (new — high value)**: `POST /api/billing/webhooks/{stripe,razorpay}`
  are PUBLIC but **signature-verified** (HMAC). Try: forged/missing signature (→401),
  replayed event (idempotent, one activation), event for an unknown tenant (ignored),
  a client trying to self-activate via `/api/billing/checkout` (stays pending). No
  entitlement changes without a verified webhook.
- **File upload**: profile photo (`PUT /api/auth/profile/photo`) — type/size, the
  scope-checked serve endpoint (`/api/auth/users/<id>/photo`, `actor_can_access`).
- **AI endpoints**: budget/throttle bypass attempts; the AI is off the request
  thread (can't block workers); failures degrade to an honest state (never fabricate).
- **CSV import** (`POST /api/admin/users/import`): malformed rows, oversized files
  (5000-row cap), injection in fields, seat-limit bypass.

## 4. Already tested (extend, don't repeat)

- Cross-tenant isolation harness, RBAC-per-role matrix, auth edges, the injection
  matrix, the 5 QA-NIGHT bugs, payment trust-boundary (9 tests), AI retry/degrade.
- See `BUGS_FOUND.md`, `docs/QA_NIGHT/*`, `docs/FUNCTIONAL_TEST_MATRIX.md`.

## 5. Honest STAGED / known list

- **Payments are TEST-MODE.** Live keys pending; `create_checkout` returns a test
  descriptor until the provider SDK call is wired (`docs/PHASE2/PAYMENTS_VERIFIED.md`).
- **Google / SSO** need the human's real OAuth creds / a real IdP to exercise the
  full round-trip (the no-JIT binding + JWT issuance are tested against a mock IdP).
- **Email/SMTP** uses the console backend in dev; production needs a provider.
- **Mobile** app is deferred to v2.
- Do **not** treat the demo seed data as production data.
