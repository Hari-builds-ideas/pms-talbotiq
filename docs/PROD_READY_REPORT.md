# PROD_READY_REPORT — production-readiness pass (Axiom PMS)

Unattended run driven by `PROD_MASTER.md`. Five build files done in order, each
committed, tests kept green throughout. Branch: `hari/agent-ui-v2`.

**Headline:** the product is named **Axiom** (reversible in one place), a real
customer can self-serve signup → import employees → sign in (password/Google/SSO)
→ upgrade through a **test-mode** payment gate, and the AI degrades gracefully
under load. What remains is provisioning + the human's real keys — nothing blocks
security/vuln testing.

---

## 1. What changed per file (with commits)

### PROD_A — Branding — `fafed5c` (+ `4c2ae61` docs)
- One central seam `frontend/src/brand.tsx` + `settings.APP_NAME` route the display
  name and every logo/favicon; legacy TalbotIQ kept as the fallback.
- Real favicons + login/sidebar/auth-page logos; email from-name + 3 subjects.
- Bundled branded-initials avatars seeded for 6 named ACME demo people.
- Verified: vitest 132/132, identity 70/70, live tab title + assets 200.

### PROD_B — Onboarding + SSO — `e3cf387` (+ `c3be0e4` docs)
- Public **self-serve signup** (`POST /api/auth/signup`): tenant + first ADMIN,
  isolated, IP-throttled, auto-login.
- **Bulk CSV import** (`POST /api/admin/users/import`, HRBP+): idempotent upsert,
  per-row errors, 2-pass reporting lines, seat + role-ceiling enforced, never
  cross-tenant.
- **Sign in with Google** via the existing allauth OIDC seam (env-gated, no JIT);
  SAML/OIDC per-tenant confirmed.
- Frontend `/signup` page + Import-CSV dialog + flag-gated Google button.
- `docs/CUSTOMER_ONBOARDING.md`. Verified: identity 74, administration 43, vitest 132.

### PROD_C — Payments (TEST MODE) — `967993e` + `3d2ed98` (+ `07dd7e0` docs)
- Models `BillingProfile/PaymentEvent/Payment/Invoice` (migration `billing/0004`).
- Stripe + Razorpay adapters with **real HMAC signature verification**; SDK-optional
  checkout; server-side price catalogue.
- **PENDING-until-verified-webhook** activation drives the existing Subscription
  state machine; idempotent + tenant-isolated webhooks; invoices; `PAYMENTS_ENABLED`
  gate. Plan-picker + invoices UI.
- Verified: `test_payments.py` 9/9, billing 86/86. `docs/PHASE2/PAYMENTS_VERIFIED.md`.

### PROD_D — AI robustness — `268aa4f` (+ `e9f35a2` docs)
- Root-caused PROVIDER_ERROR: transient 5xx weren't retried + a too-tight 30 s read
  timeout. Now retries 5xx/429/connection with jittered backoff, fails 4xx fast,
  separate env-tunable `LLM_READ_TIMEOUT` (60 s). AI confirmed off the request
  thread; graceful degrade; honest scale report.
- Verified: `test_ai_robustness.py` 6/6, AI suite 253/253. `docs/AI_ROBUSTNESS.md`.

### PROD_E — Handover package (this file)
- `.env.example` covers every new var (placeholders). `docs/SECURITY_TESTING_HANDOVER.md`,
  `docs/DEPLOYMENT_HANDOVER.md`, this report.

---

## 2. How to REVERT the branding (ONE step)

The entire rebrand — product name **and** all logos/favicon — is behind one flag:

1. In **`frontend/src/brand.tsx`** set `const REBRAND = false;` → the whole UI
   reverts to the legacy "Talbotiq PMS" leaf mark + name.
2. (Backend emails) set `APP_NAME=TalbotIQ PMS` in the env (or the `base.py` default).
3. Rebuild the frontend (`docker compose build frontend`).

The static browser-tab title/favicon live in `frontend/index.html` (revert those two
lines to `/favicon.svg` + the old `<title>` if you also want the old tab mark).

**To KEEP Axiom (make permanent):** do nothing — `REBRAND = true` is the shipped
default. Optionally delete the `LEGACY` block in `brand.tsx` once you're sure.
**To swap in different real logos:** replace the files under
`frontend/public/favicon/` and regenerate the small derivatives (the four `sips -Z`
commands are in the PROD_A progress log), then rebuild.

---

## 3. Your exact morning testing checklist (per role)

Open **http://localhost:8090**. (Run `./scripts/qa_handover.sh` first for the
automated pass; this is the human walk.)

**A. New org signup (as a brand-new customer)**
- [ ] Go to `/signup` → create "Testco" with your email → you land in the Admin Hub
  as ADMIN of a fresh, empty tenant (only you in Admin → Users).
- [ ] The welcome email prints in `docker compose logs web` (dev console backend).

**B. Import employees (as Admin/HRBP)**
- [ ] Admin → Users → **Import CSV**. Upload a small CSV
  (`name,email,role,department,designation,manager`) → see created/updated/skipped
  + any row errors. Re-upload the same file → all "updated" (no duplicates).
- [ ] A row with `role=ADMIN` uploaded by an HRBP is rejected (role ceiling).

**C. Sign in with Google (test mode)** — requires your Google creds first (§4):
- [ ] With `GOOGLE_OAUTH_*` set + `VITE_GOOGLE_SSO_ENABLED=true`, the login page
  shows "Sign in with Google" → clicking starts the Google flow → an existing
  tenant user is logged in (no new account is created — no JIT).

**D. Upgrade a plan through test-mode checkout (as Admin)**
- [ ] With `PAYMENTS_ENABLED=false` (default): Admin → Entitlements → Plans → choose
  Professional → it applies immediately, marked "no payment (test)".
- [ ] With `PAYMENTS_ENABLED=true` + Stripe test keys: choose Professional → you're
  redirected to checkout; the plan stays on the old value until the webhook fires;
  trigger the test webhook (Stripe CLI) → plan flips + an invoice appears under
  Billing history.

**E. Confirm AI degrades gracefully (as Manager `ada@`)**
- [ ] Ask for a review draft for Vera → the job runs; on a provider error it resolves
  to the calm "couldn't generate — try again" banner, **never** an infinite spinner
  and never a fabricated draft. Watch jobs in Flower (http://localhost:5555).

**Per-role spot check:** log in as `admin@ / priya@ / ada@ / akhil@ @acme.test`
(`Passw0rd!demo`) and confirm each sees only what its role allows.

---

## 4. Human to-do (before/at go-live)

1. **Logos**: the four real brand PNGs are already in `frontend/public/favicon/`.
   If you want different ones, drop them in and rebuild (§2).
2. **Google OAuth**: create the OAuth client in Google Cloud, set
   `GOOGLE_OAUTH_CLIENT_ID/SECRET` (secret store) + `VITE_GOOGLE_SSO_ENABLED=true`,
   add the redirect URI. Steps in `docs/CUSTOMER_ONBOARDING.md` §3. Test Sign-in.
3. **Payments**: set Stripe/Razorpay **TEST** keys, `PAYMENTS_ENABLED=true`, register
   the webhook URLs, wire the `create_checkout` SDK call, verify with test cards,
   THEN swap live keys — supervised (`docs/PHASE2/PAYMENTS_VERIFIED.md`).
4. **Email/SMTP**: provision a provider + set `EMAIL_*` (signup/invite/reset emails).
5. **AI scale**: managed Redis + worker autoscaling + right LLM tier + provider
   dollar-cap; size `LLM_MAX_CALLS` (`docs/AI_ROBUSTNESS.md` §7).
6. **Never commit secrets** — all new keys are env placeholders only.

---

## 5. Production-ready vs still-needs (honest)

**Ready in code (this pass + prior):** branding (reversible), self-serve signup,
CSV import, Google/SSO wiring, payments trust boundary (test mode), AI retry/degrade,
tenant isolation + RBAC + HITL + audit intact. Backend ≈1500 tests + the new suites
green; frontend 132 green.

**Needs the human / infra:** real Google + Stripe/Razorpay keys; SMTP; managed
MySQL/Redis + TLS/LB + monitoring; Celery autoscaling; the `create_checkout` SDK
call; a load test. None of these block security/vuln testing on the current build.

---

## 6. QUESTIONS / decisions made (didn't block; flag if you disagree)

- **Signup auto-logs-in** the admin (usable immediately) + sends a verify/welcome
  email; hard email-verification is a later config toggle. (Slack/Notion pattern.)
- **Google/SSO is authentication-only (no JIT)** — imported/invited users only.
  Safest for a multi-tenant HR system.
- **Imported users get no password** — they use Google/SSO or "Forgot password"
  (never email plaintext temp passwords).
- **Signup reuses the shared anon IP throttle** (100/min); a dedicated tighter
  `signup` scope is a one-line add if you want it.
- **Payments `create_checkout` returns a test descriptor** (no live SDK call yet);
  the trust boundary (signed webhook) is fully built + tested. Wire the SDK at go-live.
- **Branding source PNGs (1–2 MB) are kept**; the app serves KB-sized `sips`
  derivatives.
