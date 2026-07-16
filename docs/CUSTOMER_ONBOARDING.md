# Customer onboarding — how a new organization starts using Axiom

This is the production path for a real customer moving from “we have the PMS link” to “our employees can use it.” It is grounded in the existing multi-tenant/RBAC architecture: the tenant is the isolation boundary, JWTs carry `tenant_id` + `role`, and SSO only authenticates an already-provisioned user.

## 1. Create the workspace

1. The customer opens `/signup` and enters:
   - organization name,
   - first admin display name,
   - work email,
   - password.
2. The backend creates a new `Tenant` with a unique workspace slug, then creates the first `User` as `ADMIN` inside that tenant context.
3. The new tenant starts on the default Starter subscription/entitlement with `SIGNUP_DEFAULT_SEATS` seats.
4. The first admin receives tenant-scoped JWTs and lands in the Admin Hub.
5. A welcome/verification email is sent through the configured email backend. The account is usable immediately so the admin can finish setup; SMTP must be configured in production so this email is delivered.

### Workspace slug / login identity

For v1, the login page keeps the existing explicit **Workspace** field. Employees sign in with:

- workspace slug, e.g. `acme`,
- email,
- password or Google/SSO.

Custom domains/subdomains are deliberately left as a future deployment feature. The important security property is that the server resolves tenant from the verified workspace/SSO binding — the browser never supplies a trusted tenant id or role.

## 2. Add employees

Admins/HRBPs have two onboarding paths.

### A. Invite a few people

Use Admin → Users → Invite. The invite flow creates a pending, tenant-scoped `Invitation` row and sends/copies a signed time-limited acceptance link. The invitee sets their password and joins that exact tenant with the server-provisioned role.

Use this for small teams or late additions.

### B. Bulk import a real org

Use Admin → Users → Import CSV for large companies.

CSV header:

```csv
name,email,role,department,designation,manager
```

Where `manager` is the manager’s email address in the same tenant. Example:

```csv
name,email,role,department,designation,manager
Mira Manager,mira@example.com,MANAGER,Sales,Director,
Ravi Report,ravi@example.com,EMPLOYEE,Sales,AE,mira@example.com
```

Import behavior:

- idempotent upsert by email inside the tenant,
- creates users with unusable passwords (they sign in through Google/SSO or use Forgot password),
- validates each row and reports row-level errors without aborting the whole file,
- enforces seat limits and plan employee limits server-side,
- caps role assignment at the importer’s own role rank,
- resolves reporting lines in a second pass so a manager can appear later in the same file,
- never links a manager from another tenant.

The org chart/reporting tree is built from the imported `manager` email column. Managers then see their teams through the normal reporting-line scope rules.

## 3. Employee sign-in choices

### Password

An invited user signs in after accepting the invitation. A bulk-imported user can set a password through Forgot password if password sign-in is desired.

### Sign in with Google

Axiom uses the existing allauth OIDC seam. In production:

1. The human creates a Google Cloud OAuth client.
2. Backend env gets `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET`.
3. Frontend env gets `VITE_GOOGLE_SSO_ENABLED=true` so the login button is shown.
4. Employees must already exist in the tenant (invite/import). Google is authentication only; it does not create users or set roles.
5. At login, the workspace slug from the login page binds the Google identity to the correct tenant. The verified Google email must match an active user in that tenant.

Google Cloud console steps:

1. Create/select a Google Cloud project.
2. Configure OAuth consent screen for the customer domain.
3. Create OAuth Client ID → Web application.
4. Add authorized JavaScript origin: `https://<app-domain>`.
5. Add redirect URI for allauth OIDC callback on the deployment domain.
6. Copy the client id/secret into the deployment secret manager only; never commit them.
7. Test with a provisioned tenant user whose Google email matches their Axiom email.

### Enterprise SSO (OIDC/SAML)

SSO means the customer’s own identity provider — Google Workspace, Okta, Azure AD, ADFS, etc. — authenticates employees so the customer’s IT controls MFA, account disablement and password policy.

Axiom supports:

- generic OIDC through `django-allauth`, configured by `OIDC_*` env vars,
- SAML 2.0 per tenant through `SamlIdpConfig` and `/api/auth/saml/<tenant>/...` endpoints.

Security rules:

- no JIT self-provisioning from SSO,
- verified email required for OIDC,
- SAML assertions must be signed and replay-protected,
- role/tenant are resolved server-side from the provisioned DB user and tenant IdP config,
- SSO users land with the existing provisioned DB role unless a tenant SAML role map safely de-escalates; role escalation remains admin-controlled.

What a real customer provides:

- OIDC: issuer/discovery URL, client id, client secret, allowed redirect URI, released email claim.
- SAML: IdP entity id, SSO URL, x509 signing certificate, email/role attribute names, optional role map, and optionally a requirement for signed AuthnRequests/encrypted assertions.

See `docs/SSO.md` for the protocol-level details and mock-IdP proof.

## 4. Plan and payment gate

The self-serve tenant starts on Starter/trial seats. Upgrades and seat increases are controlled by the billing layer. In production (`PAYMENTS_ENABLED=true`, implemented in PROD_C), paid plan/seat changes remain pending until a verified Stripe/Razorpay webhook confirms payment.

## Human setup checklist

- Configure SMTP so signup/invite/reset emails deliver.
- Add Google OAuth credentials only in the deployment secret manager.
- For enterprise SSO, collect the customer’s IdP metadata and configure their tenant.
- For paid upgrades, finish Stripe/Razorpay test-mode validation, then later add live keys and flip `PAYMENTS_ENABLED=true` during go-live.

## QUESTIONS / product decisions recorded

- v1 uses the existing workspace slug field on login. Custom domains/subdomains are a future deployment feature.
- Bulk-imported users get no initial password by design; they use Google/SSO or Forgot password. This avoids emailing plaintext temporary passwords.
- SSO remains authentication-only with no open signup/JIT. This is the safest default for a multi-tenant HR system.
