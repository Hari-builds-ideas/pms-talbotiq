# PROD_B_ONBOARDING_SSO.md — how a real new customer starts using the product

**The core question this answers:** today ACME is a hand-seeded test tenant, and login only works for
existing seeded users. In production, a brand-new organization must be able to arrive at the PMS link,
create their workspace, become the admin, bring in their employees, and let those employees sign in —
including via Google / SSO. Build that, at scale, securely.

Ground everything in the EXISTING code — this app already has: multi-tenant fail-closed isolation,
tenant-scoped models, RBAC, JWT auth, invitation onboarding (PHASE2), and OIDC/SAML scaffolding
(`docs/SSO.md`, `apps/identity`). EXTEND these; do not reinvent.

## 1. New-organization signup (self-serve tenant creation)
Design + build the flow for a new company to onboard:
- A public "Create your workspace" signup: the person provides org name (→ tenant slug, unique, validated),
  their name, work email, and password. This creates: a new TENANT, the first user as that tenant's ADMIN,
  and logs them in scoped to the new tenant. Everything tenant-isolated from the first row.
- Slug/subdomain handling: decide and document how a tenant is identified at login (workspace slug field
  on the login page, as today — keep that; note custom-domain/subdomain as a future item, don't build it).
- Guard rails: email verification on signup (email is wired now), rate-limit signup, prevent duplicate
  slugs, and start the new tenant on a default plan (Starter/trial) — with the payment gate from
  PROD_C applying when they later upgrade.
- Abuse/safety: this is a public endpoint — throttle it, validate hard, and make sure a new tenant can
  NEVER see any existing tenant's data (assert with a test).

## 2. Bringing employees in (at scale)
An admin/HRBP must be able to populate their org:
- Keep + surface the existing **invitation** flow (invite by email + resend) — good for a few users.
- Add **bulk employee onboarding**: CSV import (name, email, role, department, designation, manager) that
  creates users/people in the tenant with correct roles and reporting lines, validates rows, reports
  errors per row, and is idempotent. This is how a real 5k–15k-employee company loads their org without
  inviting one by one.
- Document how reporting lines / org tree get built from the import so managers see their teams.

## 3. Sign-in with Google (OIDC) + SSO
Explain simply in the docs what SSO is (the customer's own identity provider — Google Workspace, Okta,
Azure AD — logs the user in, so employees use their existing company login and IT controls access), then:
- Wire **Sign in with Google** (OIDC) on the login screen — using the existing allauth/OIDC seam. The
  human provides the Google OAuth client id/secret as env (placeholders in `.env.example`); build +
  document the exact Google Cloud console steps the human does. Map a Google identity to the right tenant
  (via workspace slug / email domain) and the right/least-privilege role.
- Confirm the existing **OIDC + SAML** SSO paths are wired for per-tenant IdP config (a customer registers
  their IdP), tested against the mock IdP; document what a real customer provides to enable SSO.
- Security: never trust client-provided role/tenant; resolve them server-side; new SSO users land in the
  correct tenant with a safe default role that an admin can elevate.

## 4. The "how a customer starts" doc
Write `docs/CUSTOMER_ONBOARDING.md`: the end-to-end story — company gets the link → creates workspace →
verifies email → becomes admin → imports employees (CSV) or invites them → employees sign in (password or
Google/SSO) → admin sets plan (payment gate from PROD_C). This is the answer to "how will a real customer
use it".

## Rules
- Extend existing auth/tenancy; never weaken isolation or RBAC. Every new endpoint tenant-scoped +
  rate-limited + tested (including a cross-tenant isolation test for the new signup/import paths).
- Public endpoints (signup) hardened against abuse.
- Google/SSO: build the wiring + document the human's console steps; never commit real client secrets.
- Keep tests green.

## Done when
- A new org can self-serve signup → admin → import/invite employees → employees sign in (password +
  Google/SSO), all tenant-isolated and tested; `docs/CUSTOMER_ONBOARDING.md` explains it. Logged in
  PROD_PROGRESS.md, with the exact Google/SSO setup steps for the human.
