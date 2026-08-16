# PHASE2_BUILD.md — build the safe SaaS features now; design payments + auth-rewrite for review

You are a **Principal Software Architect + Senior Engineer** evolving this PMS into a multi-tenant
enterprise SaaS product. Work **fully autonomously** through the night. There are two lanes below — a
BUILD lane (implement fully, tested, committed) and a DESIGN-ONLY lane (blueprint + a ready-to-paste
Claude Code prompt, do NOT implement). Respect the split exactly.

## Why the split (do not cross it)
- The BUILD lane is additive, reversible, and safe to implement unattended.
- The DESIGN-ONLY lane is **payment-gateway integration** and any **auth token/session rewrite** — these
  touch real money and account access; they must be human-reviewed before building. Design them, write
  the prompt, but DO NOT implement them in this run. This is non-negotiable even though the rest is
  autonomous.

## Iron rules (never break)
- Ground everything in the real code (cite files). Extend what already exists — this codebase already
  has: multi-tenant fail-closed isolation, server-side RBAC, per-tenant entitlements/budgets, an audit
  log, JWT (rotate+blacklist), OIDC/SAML scaffolding, a provider-agnostic AI gateway. Do NOT reinvent
  these — build on them.
- Never weaken tenant isolation, RBAC, HITL, or the audit log.
- Root-cause work; commit per feature; keep backend AND frontend tests green after every change; add
  tests for every new feature.
- Additive DB migrations only (nullable/defaulted); zero-downtime; never a destructive migration.
- Never commit secrets; extend `.env.example` with placeholders for any new vars.
- If anything in the BUILD lane turns out to require a risky auth/payment change, STOP that item, move
  it to the design lane (write it up + a prompt), and keep going. Never guess on money or access.
- Log to `docs/PHASE2/PROGRESS.md` continuously. If context runs low, finish the current item cleanly,
  write a precise "resume here" note, and stop — /goal can resume by pointing at this file again.

---

# LANE 1 — BUILD NOW (implement fully, autonomously, tested)

## 1. Complete user profile system
For every role (Admin, HRBP, Manager, Employee; add a platform/Super-Admin role ONLY if the code clearly
needs one for cross-tenant platform ownership — otherwise document the recommendation and skip):
- Profile fields: photo (secure upload — validate type/size, store safely, tenant-scoped), full name,
  username, email, phone, employee ID, department, designation, reporting manager, organization, time
  zone, language.
- Preferences: profile preferences + notification preferences (per-channel toggles).
- Account & security surfaces: change password, change username, change email (with verification step
  stubbed if email isn't wired — see note), 2FA enable/disable (TOTP already exists — surface it),
  security settings, active sessions list, device/session management (view + revoke), login history,
  account activity, and a per-user audit view (read from the existing audit log, tenant-scoped).
- Deliver: the data model (additive migrations), the API endpoints, and the UI screens. Everything
  tenant-scoped + RBAC-correct. Add tests.

## 2. Invitation-based user onboarding (B2B pattern, not self-signup)
- Admin/HRBP invites a user by email → invite record → the invited user sets their password and joins the
  correct tenant with the assigned role. This is the standard SaaS way to add employees. Build the flow +
  API + UI + tests. (Email delivery: if SMTP is wired, use it; if not, generate the invite link and show/
  log it, and note that email delivery is pending — do NOT block on email.)

## 3. Session, device & brute-force protections (build the safe parts)
- Active-session listing + revoke, device list, login history (from real data).
- Brute-force protection: account lockout / backoff after repeated failed logins (rate-limited, using the
  existing throttle infra). This is additive and safe — build it.
- NOTE: if achieving any of this requires REPLACING the token/session scheme (a structural auth rewrite),
  do NOT do that here — document it in the design lane (item D2) and build only the additive parts.

## 4. Subscription & plan MODEL + feature entitlements (internal — NO payment gateway)
- Build the internal subscription model on top of the EXISTING per-tenant entitlement system (cite it):
  Plan (Starter / Professional / Enterprise), Subscription (tenant → plan, status: trial / active /
  past_due / grace / cancelled / expired), and the state transitions — all driven internally (an admin
  can set a tenant's plan). NO real charging yet; that's the payment lane.
- Map plans to concrete feature flags (employee limits, AI assistant, advanced analytics, check-ins,
  reviews, custom branding, SSO, audit access, API access, etc.), enforced SERVER-SIDE as the single
  source of truth.
- Feature-gating UI: the frontend hides/greys features a tenant's plan doesn't include (reuse the v1
  "hide controls the user can't use" pattern — gate off server-provided entitlements). A plan change
  updates access immediately.
- Usage tracking + limits (seats/employees) enforced server-side. Add tests. Build all of this.

## 5. Per-organization settings + branding hooks
- Org settings (name, timezone, language defaults) and per-org branding hooks (logo/color) wired so a
  tenant can be themed — additive, safe. Custom domains: document as future (design lane), don't build.

---

# LANE 2 — DESIGN ONLY (blueprint + paste-ready prompt; DO NOT implement)

Write these under `docs/PHASE2/` as complete designs the human reviews, each ending with a ready-to-paste
Claude Code implementation prompt.

## D1 — `docs/PHASE2/PAYMENTS_DESIGN.md`  (DO NOT BUILD)
Full secure payment architecture: Stripe (global) + Razorpay (India). Webhooks + signature verification,
payment verification (server-side only), subscription creation on paid event, invoice generation,
refunds, failed-payment retries, taxes (future), receipts, audit trail. Explain the end-to-end money
flow, how payment is verified securely, and explicitly what must NEVER happen on the frontend (no
client-trusted prices/entitlements, no secret keys in the SPA, no browser-side "mark paid"). How it plugs
into the LANE-1 subscription model. End with the implementation prompt. Do NOT integrate a gateway now.

## D2 — `docs/PHASE2/AUTH_REWRITE_DESIGN.md`  (DO NOT BUILD — only if a rewrite is actually needed)
Review the current auth. If the additive protections in LANE-1 item 3 fully suffice, say so and mark this
"no rewrite needed." If a structural change is genuinely required (e.g. token storage/rotation scheme,
refresh handling, concurrent-session model), design it and write the prompt — but DO NOT implement it
here, because auth changes gate account access and must be reviewed awake.

## D3 — `docs/PHASE2/SECURITY_REVIEW.md`
Complete enterprise security review grounded in the code (hashing, encryption, secrets, cookies, JWT,
CSRF, XSS, SQLi, rate limiting, API protection, RBAC, audit, PII, secure uploads, backup, DR). Current
state + prioritized fixes. Fix any trivially-safe items in LANE 1; leave structural ones as prompts.

## D4 — `docs/PHASE2/FUTURE_INTEGRATIONS.md`
Extension-seam design for Google/Microsoft login, Okta/Azure SSO, Slack, Teams, calendar, HRMS, payroll,
webhooks, public API, AI providers (gateway already agnostic), mobile (backend ready, RN frontend v2).
Adapters/interfaces so each is a plug-in, not a rewrite.

## D5 — `docs/PHASE2/DEPLOYMENT_HANDOVER.md`
Production handover for the deployment team: all env vars (extend `.env.example` with any new LANE-1 +
payment placeholders), infra, external services (DB, Redis, email, AI, payment, object storage for
photos/invoices), monitoring, logging, backup, health checks, SSL, domains + future custom-domain notes.
Placeholders only.

---

# FINISH

## `docs/PHASE2/ROADMAP.md`
- What was BUILT in this run (LANE 1), with commits, and how to test each.
- What is DESIGNED and awaiting the human (LANE 2: payments, any auth rewrite), each with its prompt.
- The recommended order to build the design-lane items (payments after you've reviewed the design).
- A clear line: payments + auth-rewrite were intentionally NOT built unattended — they're staged for
  human-reviewed daylight builds because they involve money and account access.

## `docs/PHASE2/FINAL_TESTING_CHECKLIST.md`
The exact per-role checklist for the human to verify the LANE-1 features (profiles, invites, sessions,
lockout, subscription/plan gating, org settings) work end to end.

Do all of LANE 1. Design (not build) all of LANE 2. Only stop when both are done, or at a clean,
documented resume point.
