# WEB_COE_REPORT — closing the COE web/back-end gaps

Unattended build per `WEB_BUILD_COE.md` (with `COE_REQUIREMENTS_MAP.md` + `BUILD_0_READ_FIRST.md`),
on Claude Opus, extra effort. Three phases, each committed + pushed to `main`:

| Phase | Commit |
|---|---|
| W1 — SSO: SAML + OAuth proven | `b5314c0` WEB_COE W1 — SSO SAML + OAuth proven |
| W2 — WCAG 2.1 AA pass + a11y guard | `45994c5` WEB_COE W2 — WCAG 2.1 AA pass + a11y guard |
| W3 — functional test matrix (web) | `cbec37c` WEB_COE W3 — functional test matrix (web) |

**Suite movement:** backend **1171 → 1193** passing (+22: 14 SSO, 8 functional-gap), 2
deselected. Frontend **43 → 72** vitest (+15 axe a11y, +14 token-contrast). tsc/eslint/
production build clean. No regressions.

---

## W1 — SSO (OIDC/OAuth + SAML 2.0)

**As-built.** Both protocols authenticate and then mint our existing tenant-scoped JWT
(`issue_tokens_for_user`); RBAC/scope/MFA downstream are unchanged. SSO can never change
which tenant a session belongs to.

- **OIDC/OAuth** (pre-existing, now verified end-to-end): allauth generic `openid_connect`
  → `TenantSocialAccountAdapter` (verified-email required, no JIT, tenant-scoped binding,
  no cross-tenant) → `OidcCompleteView` mints the JWT. Tests: `apps/identity/tests/test_oidc.py` (9).
- **SAML 2.0 SP** (new — `apps/identity/saml/`): `python3-saml` (OneLogin SP toolkit; chosen
  over djangosaml2 because it validates the assertion and returns attributes while we keep
  our own JWT — see DECISIONS D25). Per-tenant `SamlIdpConfig` (public IdP entity-id/SSO-url/
  signing-cert + attribute names + role_map + `sp_private_key_secret_ref` — secrets referenced
  by env-var name, never in DB/git). Endpoints `saml/<tenant>/{metadata,login,acs}`. Forced
  signature + strict conditions (expiry/audience/destination), SHA-256, Redis SET-NX replay
  guard. Attribute→role mapping JIT-syncs the DB role (RBAC enforces the DB role, not the
  token claim) + writes an audit row; empty role_map ⇒ Hub stays authoritative.

**Proof.**
- **[test]** `test_saml.py` (12): a real **xmlsec-signed** mock-IdP round-trip — happy path,
  tampered assertion rejected, unsigned rejected, expired rejected, replay rejected,
  **tenant isolation** (tenant A's IdP can't mint a tenant B session), unknown identity
  denied, attribute→role sync + audit, role fallback, metadata, login 302, not-configured 404.
- **[live]** On the running stack: metadata 200; a signed ACS round-trip minted the JWT with
  the mapped role + correct tenant; `/me` with the SSO JWT 200; a replay → 401 `saml_replay`.
- **docs/SSO.md** — per-tenant setup, the three isolation locks, the proof, and the real-IdP needs.

**🔑 Customer/infra (not a code task):** a **real production IdP** (Okta / Azure AD / Google
Workspace / ADFS) per tenant — proven here against a self-signed mock IdP; TLS 1.2+ in front
of the ACS; an SP private key (provisioned as a secret via `sp_private_key_secret_ref`) only
if a tenant's IdP demands signed AuthnRequests / encrypted assertions; the OIDC client secret.

## W2 — WCAG 2.1 Level AA (desktop Admin Hub)

**Audit + guards** (`frontend/src/test/a11y/`): axe-core (vitest/jsdom) over 14 key screens
in the real shell + the ⌘K palette, asserting **zero** A/AA violations; plus a token-contrast
test asserting every text pair ≥ 4.5:1. Chose axe-in-jsdom over Playwright to fit the existing
test stack (DECISIONS D26).

**Before → after:** axe A/AA violations **7 → 0** (unlabeled selects/inputs, command-palette
dialog name); contrast failures **7 → 0** (six badge tones + muted-foreground, fixed by
darkening the tone tokens).

**Fixes:** aria-labels on filter selects/inputs; skip-to-content link + `<main>` target;
labelled primary nav; Topbar icon-button labels; a **keyboard alternative to the nine-box
drag** (per-chip "Move to box" menu, WCAG 2.1.1); command-palette dialog title (4.1.2); a
global visible focus outline (2.4.7); `prefers-reduced-motion` (2.3.3).

**Honesty (docs/ACCESSIBILITY.md):** axe-in-jsdom catches a real but **partial** slice of AA;
color-contrast is covered by the token check (not pixels over images/charts), and a manual +
assistive-technology pass (screen-reader walkthrough, zoom/reflow at 400%/320px, real
keyboard traversal of every overlay) is still owed before any **certified full-conformance**
claim. The accurate position: **automated-AA clean + the listed manual items** — we do not
claim certified full WCAG 2.1 AA from automated testing alone.

## W3 — Functional test matrix (web)

**docs/FUNCTIONAL_TEST_MATRIX.md** maps each brief behaviour → test(s) → status. Most were
already covered; W3 filled the genuine gaps (+8 tests):
- Review transitions: `route_rejected` (APPROVED→EDITING) + its illegal-unless-APPROVED guard.
- Approval escalation: **PARALLEL** step escalation (independent of its active sibling).
- Notifications: **delivery** generation (signal → integrations receiver → notifier) for
  approval assignment, escalation, and feedback invitations.
- KPI weight = 100.00 enforced on **PATCH** (edit), not only create/add/delete.

KPI = 100 boundary cases (99.99 / 100.01 / exactly 100) were already covered (validators +
API create boundary tests); confirmed and cited.

**Proof.** **[test]** backend 1193 passing. **[live]** `POST /api/goals` KPI 99.99→400 /
100.01→400 / 100.00→201; a seeded overdue route + the real `escalate_overdue_routes()` task →
`{scanned:1, escalated:1, errors:0}`, step reassigned MANAGER→HRBP, route IN_PROGRESS; the
notifier path fired live (Slack no-op, graceful).

---

## 🔑 Brief items that are NOT code tasks (flagged, not faked)

These are the customer's / infrastructure's to provide; documented, not pretended-delivered:

- **A real production IdP** (Okta / Azure AD / etc.) for live SSO — proven here against a mock IdP.
- **TLS 1.2+ in transit** and **AES-256 at rest** — load-balancer / DB / disk configuration.
- **Third-party penetration testing** — an external vendor engagement.
- **The production LLM key** (Gemini/Groq) — provisioned via env; the gateway is provider-agnostic.
- **User manuals** (<2-hour-training UI guide + technical docs) — a written deliverable, separate from code.
- **WCAG full-conformance certification** — needs the manual/AT pass documented in docs/ACCESSIBILITY.md.

## Verification honesty key
**[test]** asserted by an automated test in the suite · **[live]** exercised over real HTTP /
the real Celery task on the running stack · **[build]** typecheck/lint/production-build only.

## What's next (separate from this build)
The MOBILE build (`COE/MOBILE_BUILD_COE.md`) — 1:1 Meeting Notes backend + the mobile screens —
and the paused `MOBILE_MOCK_ADAPTATION.md` Step 2. They don't conflict with this web work.
