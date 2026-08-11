# Axiom PMS — production readiness checklist

Branch `hari/prod-hardening`. Every "done" below was **verified by running something**,
not by reading code; the evidence is in `docs/PROD/PROGRESS.md`.

## Production-ready: **NO — but the security tier is done**

Nothing in Tier 1 is outstanding as *engineering*. What remains is (a) configuration only
a human can supply, and (b) four product gaps, one of which you cannot legally sell
without.

### Blockers before a real company uses this

| # | Blocker | Who |
|---|---|---|
| B1 | **Legal pages** — no Privacy Policy or Terms exist. You are processing employee performance data; in the EU/UK that is GDPR-regulated. Not sellable without them. | human (item 15) |
| B2 | **SMTP credentials** — without them nobody can accept an invite or reset a password. Code is done and proven; the account is not. | human (item 3) |
| B3 | **Domain + DNS** for TLS, and `:80`/`:443` open. | human (item 1) |
| B4 | **Offsite backups** — `S3_BUCKET` is unset, so every backup currently shares a disk with the database it protects. | human (item 5) |
| B5 | **A working Gemini key** — the one in `.env` is rejected by Google (401, wrong credential type). AI degrades to a clean 503, so this blocks the AI story, not the app. | human |
| B6 | **Secret store decision** — `.env` on a host is the weakest link once real customer data lands. | human (item 2) |

None of B1–B6 needs more code.

---

## The 16 items

### Tier 1 — security & deployment

| # | Item | Status | What changed | Human must |
|---|---|---|---|---|
| 1 | HTTPS/TLS behind Caddy | ✅ **done** | New `Caddyfile` + `caddy`/`frontend` services; Caddy is the only container publishing a port. **Found and fixed a security bug the proxy introduced**: DRF keyed the anon throttle on a client-writable header, so rotating a forged `X-Forwarded-For` bought a fresh rate-limit bucket every request. `NUM_PROXIES` fixes it. | Point `DOMAIN` at the host, open `:80`+`:443`, set `ACME_EMAIL`; back up `caddy_data` |
| 2 | Secrets | ✅ **done** | Scanned **all 444 commits**: no credential ever committed, `.env` never tracked. New `docs/PROD/ENVIRONMENT.md`; two regression guards | Choose a secret store; rotate the Gemini key |
| 3 | Real email/SMTP | ✅ **done** | Code was already right and is **proven over a real SMTP socket**. Added deploy checks so a console backend or localhost `PUBLIC_APP_URL` now **fails the deploy** instead of silently swallowing every reset and invite | Provide SMTP creds; complete SPF/DKIM |
| 4 | Headers + rate limiting | ✅ **done** | HSTS, secure/httponly/samesite cookies, `X-Frame-Options: DENY`, nosniff, CSRF origins all verified; tenant/user/anon throttles + login lockout. Real gap was the forgeable throttle (item 1) | `DJANGO_NUM_PROXIES=2` behind a CDN; consider a WAF |
| 5 | Backups + restore | ✅ **done** | New `backup_db.sh` (self-verifying) + `restore_db.sh` (drill-by-default). **Round-trip tested for real**: 27M dump → 78 tables, 6 tenants, 80,914 users restored; a truncated dump correctly refused | Set `S3_BUCKET`, schedule the cron, calendar the monthly drill |
| 6 | Health + monitoring | ✅ **done** | `/healthz` 200, `/readyz` 200 naming every dependency, `/metrics` 401 (token-gated, not disabled). Sentry already correct. Added a *Reading the logs* runbook | Set `SENTRY_DSN`, `METRICS_TOKEN`; ship logs off-host |

### Tier 2 — onboarding & multi-tenancy

| # | Item | Status | Evidence | Human must |
|---|---|---|---|---|
| 7 | Self-serve signup | ✅ **done** | 16 tests green across signup + invitations (workspace creation, first admin, invite accept) | Nothing — but it is only *usable* once SMTP exists (B2) |
| 8 | CSV bulk import | ✅ **done** | Per-row errors `{row, email, error}`; one bad row never aborts the import; seat limit + role ceiling enforced server-side; manager lines resolved in a second pass | Nothing |
| 9 | Empty-state UX | ✅ **done** | Shared `EmptyState` component used across **19** screens | Spot-check a brand-new tenant visually |
| 10 | Roles/permissions | ✅ **done** | 8/8 RBAC + 7/7 cross-tenant isolation in the 131-check handover suite; 97 billing/entitlement tests | Nothing |

### Tier 3 — completeness & polish

| # | Item | Status | Reality | Human must |
|---|---|---|---|---|
| 11 | Per-tenant AI config | ❌ **missing** | There is no per-tenant key storage and no AI on/off toggle. The Gemini key is a **single server env var**, so every tenant shares one key and one bill, and an admin cannot rotate or disable AI themselves | Decide: acceptable for early customers (you operate the key), or build it |
| 12 | Cost controls | 🟡 **partial** | *Enforcement exists* — `AgentBudget` is per-tenant, and the global ceiling works (it tripped during testing). *Visibility does not* — `ai_usage` is a CLI command; there is no admin-facing usage/cost endpoint or screen | Build the admin view, or report cost manually |
| 13 | Billing/plan gating | ✅ **done** | Starter/Professional/Enterprise with server-side entitlement gating; 97 tests, and the handover suite proves a plan flip changes feature access server-side | Payments stay in test mode until you go live |
| 14 | Accessibility + responsive | 🟡 **partial** | **a11y verified**: 29 tests, axe WCAG 2.1 A/AA clean across Admin Hub screens including the command palette. **Responsive not verified by me** — no phone-browser pass was run | Walk the app on a real phone before demoing it as mobile-ready |
| 15 | Legal/marketing pages | ❌ **missing** | No Privacy Policy, no Terms, no support contact anywhere in the app | **Blocker B1.** Needs real legal text, not placeholder |
| 16 | Product docs / in-app help | ❌ **missing** | No getting-started or help surface for a new admin. (The chat has a "How to use" affordance with example prompts, but that is chat-specific) | Write it, or accept a guided first call with each customer |

---

## Score

- **Tier 1 (security & deployment): 6/6 done.** This is the tier that decides whether it
  is *safe* to put a real company on it.
- **Tier 2 (onboarding): 4/4 done.**
- **Tier 3 (polish): 1 done, 2 partial, 3 missing.** This is the tier that decides
  whether it is *sellable*.

## What I did not do, and why

- **Did not build items 11, 15, 16.** Each is a real feature (per-tenant key management,
  legal copy, a help surface), not a hardening task. Item 15 in particular needs a
  lawyer's text, and shipping a plausible-looking placeholder privacy policy would be
  worse than shipping none — it reads as a promise you have not actually made.
- **Did not verify responsive on a phone.** I can assert the a11y suite passes because I
  ran it; I have no device and would only be guessing.
- **Did not weaken** tenant isolation, RBAC, HITL or the audit log anywhere. The one
  security-relevant change (`NUM_PROXIES`) tightened a control that terminating TLS
  would otherwise have silently removed.

## Suggested order from here

1. B1 legal pages (blocks selling), B2 SMTP (blocks onboarding) — both human-supplied.
2. B3/B4 domain + offsite backups — an afternoon of ops.
3. Item 12's admin usage view — small, and it is what stops a surprise AI bill.
4. Item 11 per-tenant keys — only once you have more than a couple of customers.
5. Item 16 in-app help — replaceable by a guided onboarding call at first.
