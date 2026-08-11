# Axiom PMS — production readiness checklist

Branch `hari/prod-hardening`. Every "done" below was **verified by running something**,
not by reading code; the evidence is in `docs/PROD/PROGRESS.md`.

## Production-ready: **NO — but every remaining blocker is yours, not the code's**

All 16 items are now built as far as is possible without human-supplied inputs. Nothing
is outstanding as *engineering*. What remains is configuration, one piece of legal text,
and one deliberate refusal (per-tenant API key storage — see item 11).

### Blockers before a real company uses this

| # | Blocker | Who |
|---|---|---|
| B1 | **Legal text.** The Privacy/Terms **pages, routes and links now exist**, carrying a visible "Draft — pending legal review" banner. You process employee performance data (GDPR-regulated in the EU/UK), so the bodies need counsel's words before you sell. A test asserts the banner, so removing it is a deliberate line in a diff. | human (item 15) |
| B2 | **SMTP credentials** — without them nobody can accept an invite or reset a password. The code is done and proven over a real socket, and the deploy check now *fails* rather than silently swallowing mail. | human (item 3) |
| B3 | **Domain + DNS** for TLS, and `:80`/`:443` open. | human (item 1) |
| B4 | **Offsite backups** — `S3_BUCKET` unset, so every backup shares a disk with the database it protects. | human (item 5) |
| B5 | **A working Gemini key** — the one in `.env` is rejected by Google (401, wrong credential type). AI degrades to a clean 503, so this blocks the AI story, not the app. | human |
| B6 | **Secret store decision** — `.env` on a host is the weakest link once real customer data lands. | human (item 2) |
| B7 | **Set `VITE_SUPPORT_EMAIL`** — it falls back to an obvious `support@example.com` placeholder rather than a plausible address nobody reads. | human (item 15) |

None of B1–B7 needs more code.

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
| 11 | Per-tenant AI config | 🟡 **switch done, keys refused** | **Built:** a per-tenant AI off switch enforced at the `LLMGateway` — both `run()` and `run_tools()`, so the chat assistant is covered too. Stored in `TenantConfig.settings` (no migration; inherits the audit trail). Absent ⇒ ON. Fails open, because it is a preference, not a security control. 9 tests. **Refused:** per-tenant API key storage — see below | Decide whether one operator-held key is acceptable (it is, for early customers) |
| 12 | Cost controls | ✅ **done** | `GET /api/billing/ai-usage` (admin): calls, tokens, estimated cost, by-agent and by-model breakdowns, budgets in force. Tenant taken from the caller — no parameter can widen it (2 isolation tests). Unpriced models named, never counted as free. 10 tests | Nothing |
| 13 | Billing/plan gating | ✅ **done** | Starter/Professional/Enterprise with server-side entitlement gating; 97 tests, and the handover suite proves a plan flip changes access server-side | Payments stay in test mode until you go live |
| 14 | Accessibility + responsive | ✅ **done** | **a11y**: 29 tests, axe WCAG 2.1 A/AA clean. **Responsive now verified** on an emulated iPhone 13 — and it was **broken**: the sidebar started open at every width, leaving a phone ~130px of content with the dashboard cards overlapping. Fixed (overlay + backdrop below `lg`); desktop asserted unchanged. 4 tests | Glance at it on a real handset — emulation is close, not identical |
| 15 | Legal/marketing pages | 🟡 **structure done, text pending** | `/privacy`, `/terms`, `/support` exist as **public** routes (outside the auth guard), linked from the login page, with a visible draft banner and a configurable support address. 5 tests | **B1** — replace the bodies with counsel's text, then delete the banner |
| 16 | Product docs / in-app help | ✅ **done** | `/help`, role-aware: a six-step admin setup path ordered to avoid this product's real dead ends (people → reporting lines → cycle → goals), or a short orientation for everyone else. In the sidebar for all roles | Nothing |

---

## Score

- **Tier 1 (security & deployment): 6/6 done.** This is the tier that decides whether it
  is *safe* to put a real company on it.
- **Tier 2 (onboarding): 4/4 done.**
- **Tier 3 (polish): 4 done, 2 partial, 0 missing.** The two partials are partial by
  choice, not omission: item 15 waits on a lawyer, item 11 on a KMS decision.

## What I did not do, and why

- **Did not store per-tenant API keys.** Accepting a customer's Gemini key into MySQL
  needs envelope encryption with a KMS-held key, a rotation path, and a guarantee it
  never reaches a log or an error report. A plaintext credential in a JSON column would
  be a security regression dressed as a feature — an architecture decision for you, not
  something to slip into a hardening pass.
- **Did not write the legal text.** The pages, routes, links and support address exist;
  the words need counsel. A plausible-looking placeholder policy is worse than an
  obviously-draft one, because a customer's legal team skims it and assumes sign-off —
  hence the banner, and the test that keeps it there.
- **Did not test on physical hardware.** Responsive is verified under Chrome device
  emulation at 390×844, which is close to but not the same as a real handset.
- **Did not weaken** tenant isolation, RBAC, HITL or the audit log anywhere. Two changes
  tightened things: `NUM_PROXIES` restored a rate limit that terminating TLS would have
  silently removed, and the AI switch is enforced server-side at the gateway rather than
  by hiding buttons.

## A note on what automation missed

The responsive sweep reported **no horizontal overflow on any of ten authenticated
routes** — and the dashboard was unusable on a phone, with stat cards drawn on top of
each other. `scrollWidth` equalled the viewport because nothing overflowed; the layout
was simply broken inside it. The check was measuring the wrong property, and only a
screenshot showed it. Worth remembering when reading any green result here.

## Suggested order from here

1. **B2 SMTP** — nothing else matters if nobody can accept an invite. An hour with a
   provider account, then `manage.py check --deploy` tells you whether you got it right.
2. **B3 domain + B4 offsite backups** — an afternoon of ops, and B4 is the one that
   stops a bad day becoming a fatal one.
3. **B1 legal text** — the only thing between you and selling. Send counsel the drafts
   at `/privacy` and `/terms`; the structure is done.
4. **B5/B6/B7** — a working Gemini key, a secret store, a real support address.
5. **Item 11 per-tenant keys** — only when a customer actually asks to bring their own,
   and only with a KMS.
