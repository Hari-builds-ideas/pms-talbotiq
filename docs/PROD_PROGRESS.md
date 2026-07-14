# PROD_PROGRESS — unattended production-readiness run

Run driver: `PROD_MASTER.md` → A (branding) → B (onboarding/SSO) → C (payments) →
D (AI robustness) → E (handover). Logged after each file. Branch: `hari/agent-ui-v2`.

---

## PROD_A — Branding ✅ (commit `fafed5c`)

**Goal:** product looks finished and is named **Axiom** everywhere, from ONE place,
fully reversible to the legacy "Talbotiq PMS" identity.

### What changed
- **One central seam** `frontend/src/brand.tsx` — `BRAND` config + `BrandMark`/
  `BrandWordmark` components. A single `const REBRAND = true` flips the whole
  rebrand (name **and** every logo/favicon) back to the legacy leaf mark. The
  display name also honours `VITE_APP_NAME` env override. Legacy values kept as
  the fallback block.
- **Backend name** `settings.APP_NAME` (env `APP_NAME`, default `Axiom`) — drives
  `DEFAULT_FROM_EMAIL` and the 3 email subjects (invite / password reset / email
  change) in `apps/identity/{invite_views,views,profile_views}.py`.
- **Favicon** — real PNG favicons (16/32/180/192/512) generated from the green
  icon mark, wired in `frontend/index.html`; tab title + OG/meta now "Axiom".
- **Logos wired** — login brand panel (white wordmark on dark), sidebar header
  (green mark + short name), the two public auth pages (invite / reset lockups).
  All via the seam; the per-tenant `custom_branding` logo override is untouched.
- **Assets** — human's 4 source PNGs kept at `frontend/public/favicon/`
  (`icon-green/white`, `logo-green/white`); web-optimized derivatives generated
  under `frontend/public/brand/` + root favicons (sips, KB-sized).
- **Avatars** — UI already had initials-fallback avatars (kept). Added bundled
  **branded-initials avatar fixtures** (`apps/core/management/commands/demo_avatars/*.png`)
  seeded onto 6 named ACME demo people in `seed_demo_rich` (deterministic, ACME-only,
  no external fetch, no runtime image dep — the container has no Pillow, so the PNGs
  are pre-generated). Idempotent: never overwrites an uploaded photo.

### Verified
- Frontend `tsc --noEmit` clean; **vitest 132/132** green (incl. axe a11y).
- Backend `manage.py check` clean; **identity suite 70/70** green.
- Live on `http://localhost:8090`: tab title `Axiom · Admin Hub`; favicons +
  `/brand/*` assets all serve 200 `image/png`.
- Reseed OK ("seeded 4 demo avatars" — 2 already had uploads); all 6 named people
  stream their avatar 200 via the authenticated photo endpoint.

### How to REVERT the branding (one step)
Set `REBRAND = false` in `frontend/src/brand.tsx` and `APP_NAME=TalbotIQ PMS` in
the env (or the base.py default). Rebuild the frontend. Full detail in
`docs/PROD_READY_REPORT.md` (written in PROD_E).

### Human to-do
- The real logo source PNGs are in place; to swap them, replace the files under
  `frontend/public/favicon/` and regenerate the derivatives (documented in the
  final report), then `docker compose build frontend`.

### QUESTIONS / decisions made
- Chose to keep the human's 1–2 MB source PNGs in `favicon/` and ship KB-sized
  `sips`-generated derivatives for the actual `<img>`/favicon refs (source PNGs are
  too heavy to serve directly). No decision needed from the human.

---

## PROD_B — Onboarding + SSO ✅ (commit `e3cf387`)

**Goal:** how a real new customer starts — self-serve signup, bulk employee import,
and Sign-in-with-Google — all tenant-isolated and RBAC-safe.

### What changed
- **Self-serve signup** `POST /api/auth/signup` (`apps/identity/signup_views.py`,
  PUBLIC, `AtomicAnonThrottle`) — creates a `Tenant` + first `ADMIN` inside
  `tenant_context`, provisions a Starter subscription + `SIGNUP_DEFAULT_SEATS`
  seats, sends a best-effort welcome email, and auto-logs-in (device session +
  tenant-scoped JWTs). Role is forced ADMIN server-side; unique-slug handling
  (suffix on collision, reserved-slug list); hard input + password validation.
- **Bulk CSV import** `POST /api/admin/users/import` (`EmployeeImportView`,
  INVITE_USERS = HRBP+). Accepts a multipart CSV (`name,email,role,department,
  designation,manager`) or JSON rows. Idempotent upsert by email; per-row errors
  never abort the file; **two-pass** reporting-line linking by manager email;
  **seat + role-ceiling enforced** server-side; **never links a manager from
  another tenant**. Imported users get an unusable password → they sign in via
  Google/SSO or "Forgot password" (no plaintext password ever transmitted).
- **Sign in with Google (OIDC)** — added a Google app to the allauth
  `openid_connect` provider, appended only when `GOOGLE_OAUTH_CLIENT_ID` is set,
  bound through the SAME no-JIT `TenantSocialAccountAdapter`. `GOOGLE_SSO_ENABLED`
  setting. Confirmed the existing per-tenant SAML + generic OIDC paths are intact.
- **Frontend** — new `/signup` page (SignupPage.tsx), a "Create your workspace"
  link + a flag-gated ("Sign in with Google") button on the login page, and an
  "Import CSV" dialog on Admin → Users with a per-row result summary.
- **Env** — `.env.example` + `frontend/.env.example`: `APP_NAME`,
  `SIGNUP_DEFAULT_SEATS`, `GOOGLE_OAUTH_CLIENT_ID/SECRET`, `VITE_GOOGLE_SSO_ENABLED`
  (placeholders). **docs/CUSTOMER_ONBOARDING.md** — the end-to-end customer story.

### Verified
- **Live**: signup → 201, fresh isolated tenant (admin sees only itself), duplicate
  org → distinct slug, weak/empty input → 400/422. CSV import → created/updated/
  skipped counts, 2-pass manager link, dept/title persisted, unusable password,
  HRBP-imports-ADMIN blocked, Employee → 403, cross-tenant manager → row error.
- **Tests**: `apps/identity` 74/74, `apps/administration` 43/43 (incl. new
  `test_signup.py`, `test_employee_import.py` + shared `org` conftest). Frontend
  `tsc` clean, **vitest 132/132**. `/signup` + `/login` serve 200 on :8090.

### Decisions (also in CUSTOMER_ONBOARDING.md)
- Signup **auto-logs-in** the admin (usable immediately) + sends a verify/welcome
  email; hard email-verification enforcement is a later config toggle (matches the
  Slack/Notion "you're in, verify later" pattern).
- Google/enterprise SSO stays **authentication-only (no JIT)** — imported/invited
  users only; safest default for a multi-tenant HR system.
- The exact allauth Google login URL (`/accounts/oidc/google/login/…`) is wired but
  can only be end-to-end verified once the human adds real Google creds (documented).

### QUESTIONS
- Signup reuses the shared `anon` IP throttle (100/min). A dedicated tighter
  `signup` scope is a one-line `DEFAULT_THROTTLE_RATES` add if desired.

---

## PROD_C — Payments (Stripe + Razorpay, TEST MODE) ✅ (commits `967993e`, `3d2ed98`)

**Goal:** a paid plan/seat change requires REAL payment before the entitlement
activates — verified end to end against test-mode signature schemes.

### What changed
- **Models** (additive, `billing/0004`): `BillingProfile`, `PaymentEvent`
  (`(provider,event_id)` UNIQUE → idempotency), `Payment`, `Invoice` (seq number).
- **Provider port** + Stripe/Razorpay adapters with **real HMAC signature
  verification** (self-contained, no SDK). Checkout is SDK-optional (test
  descriptor now; live SDK call marked TODO for go-live).
- **Service**: `start_checkout` (server-side price catalogue) + `process_webhook`
  (verify → idempotent → drive existing `set_plan`/`set_subscription_status` →
  `Payment` + `Invoice` + audit).
- **Endpoints**: `payments-config`, `checkout`, `invoices` (admin) + PUBLIC
  signature-verified `webhooks/{stripe,razorpay}`. `PAYMENTS_ENABLED` gate.
- **Frontend**: plan-picker (monthly/annual) → checkout redirect + invoices list
  on the Billing page.
- **Env + docs**: `.env.example` (PAYMENTS_ENABLED + all Stripe/Razorpay
  placeholders), `docs/PHASE2/PAYMENTS_VERIFIED.md` (build + go-live steps).

### Verified
- **Tests** `apps/billing/tests/test_payments.py` 9/9 + full billing suite 86/86.
  Covered: pending-until-webhook, invalid-signature→401, idempotency, cross-tenant
  isolation, no-client-trusted-activation, failed→PAST_DUE, Razorpay, disabled-flip.
- **Live**: payments-config 200 (admin) / 403 (employee), invoices 200, unsigned
  webhook → 401. Frontend `tsc` clean + vitest 132/132.

### QUESTIONS / staged
- `create_checkout` returns a test descriptor until the provider SDK call is wired
  (documented go-live step 4). Reconciliation beat job + refund admin endpoint are
  follow-ups (per PAYMENTS_DESIGN §5).
