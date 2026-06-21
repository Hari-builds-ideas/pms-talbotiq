# WEB_BUILD_COE — close the COE web/back-end gaps (SSO/SAML + WCAG 2.1 AA)

> Read BUILD_0_READ_FIRST.md and COE_REQUIREMENTS_MAP.md IN FULL first; all BUILD_0 rules apply (code-
> only against the existing stack; never weaken RBAC/scope/tenant isolation/HITL/anonymisation; backend
> suite never regresses + grows; frontend build/tsc/lint clean; commit+push per phase; .env never staged;
> PROGRESS/DECISIONS/QUESTIONS updated; almost zero LLM calls). This build closes the WEB + BACK-END
> requirements the COE brief grades that aren't done: SSO/SAML proven, and WCAG 2.1 AA on the desktop hub.

---

## Phase W1 — SSO: SAML + OAuth, proven round-trip

The brief requires "SSO (SAML/OAuth)". OAuth/OIDC is wired via allauth but not proven; SAML isn't done.
- Verify/complete OIDC end-to-end against a test IdP (or a local mock IdP / a documented dev IdP config):
  the login handoff → callback → a tenant-scoped user session/JWT, with RBAC role mapping. Capture the
  round-trip.
- Add SAML 2.0 SP support (a maintained library, e.g. python3-saml / djangosaml2 — pick one, justify in
  DECISIONS.md): SP metadata, ACS endpoint, attribute → user/role mapping, tenant binding, signed
  assertions. Multi-tenant: each tenant configures its own IdP (config-driven, secret_ref for any
  secret — never committed).
- Keep our existing JWT session model: SSO authenticates, then issues our normal tenant-scoped JWT;
  RBAC/scope unchanged downstream. MFA still applies where required.
- Tests: OIDC + SAML auth flows (mocked IdP), attribute→role mapping, tenant isolation (an IdP for
  tenant A can't mint a tenant B session), signature validation, replay/expiry handling.
- 🔑 A REAL production IdP (Okta/Azure AD/etc.) is the customer's to provide — document the per-tenant
  config steps in docs/SSO.md; prove the flow against a test/mock IdP here.

**Verify [test]+[live]:** OIDC + SAML round-trips pass against a test/mock IdP; tenant isolation asserted;
docs/SSO.md written. Commit `WEB_COE W1 — SSO SAML + OAuth proven`.

## Phase W2 — WCAG 2.1 Level AA accessibility pass (desktop Admin Hub)

The brief requires "WCAG 2.1 Level AA compliant". Make it real and verifiable.
- Audit the desktop hub against WCAG 2.1 AA: run an automated pass (axe-core / @axe-core/react or a
  Playwright+axe script) across the key screens (login, dashboards, reviews, goals/KPIs, JD generation,
  org chart, calibration/moderation, succession, analytics, admin, audit). Capture the violations.
- FIX the AA-level issues: semantic landmarks/headings, all form inputs labelled + associated, focus
  order + visible focus rings, keyboard operability of every interactive control (menus, dialogs,
  the cmdk palette, the nine-box drag — provide a keyboard alternative to drag), color-contrast ≥ 4.5:1
  (3:1 for large text/UI) on text + status badges, aria for custom widgets (tabs, dialogs, comboboxes),
  alt text / aria-labels on icon-only buttons, error messages programmatically associated, no
  keyboard traps, skip-to-content link, respects reduced-motion.
- Add an automated a11y test (axe in CI/test) over the main screens so AA can't silently regress, and
  write docs/ACCESSIBILITY.md (the standard, what was fixed, the automated guard, known caveats + the
  manual-audit items that still need a human/AT pass — be honest that automated catches ~a subset).

**Verify [test]+[build]:** the axe pass reports zero AA violations on the audited screens (or documents
each accepted exception with rationale); the a11y test guards it; frontend build/tsc/lint clean. Commit
`WEB_COE W2 — WCAG 2.1 AA pass + a11y guard`.

## Phase W3 — Cross-surface functional verification (the brief's testing row, web side)

The brief grades: review-cycle transitions, automated notifications, KPI weightage = 100%, approval
escalations — "across both desktop and mobile web views". Verify the WEB/desktop side rigorously.
- Add/confirm tests that EXERCISE: every review state transition; the KPI weight = 100.00 validation
  (boundary cases: 99.99, 100.01, exactly 100); approval escalation (sequential + parallel, the timeout/
  escalation sweep); notification generation on the key events. Where a gap exists, fill it.
- Produce docs/FUNCTIONAL_TEST_MATRIX.md mapping each brief-required behaviour → the test(s) that prove
  it → pass status. This is the artifact that answers "did you verify what the brief asked".

**Verify [test]+[live]:** the matrix's behaviours are each test-backed and green; live-confirm the KPI=100
rule + one escalation on the running stack. Commit `WEB_COE W3 — functional test matrix (web)`.

---

## End of WEB_BUILD_COE
Write `WEB_COE_REPORT.md`: SSO (OIDC+SAML) as-built + the test/mock-IdP proof + what a real IdP needs;
the WCAG 2.1 AA audit (before/after violation counts) + the guard + honest manual-audit caveats; the
functional matrix; commit list; [test]/[live]/[build] honesty; the 🔑 items still owed (real IdP, TLS/
AES, pen-test, manuals). Then the MOBILE build can run (or in parallel if you prefer — they don't
conflict).
