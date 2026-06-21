# SSO — OIDC/OAuth + SAML 2.0 (per-tenant, config-driven)

The brief requires **SSO (SAML/OAuth)**. Both protocols are implemented and proven
against a test/mock IdP. They share one rule: **SSO only authenticates — it then
issues our normal tenant-scoped JWT** through `issue_tokens_for_user`, and every
downstream check (tenant isolation, RBAC, MFA where required) is unchanged. SSO can
never change *which tenant* a session belongs to.

| | OIDC / OAuth | SAML 2.0 |
|---|---|---|
| Library | `django-allauth` (`openid_connect`) | `python3-saml` (OneLogin SP toolkit) |
| Where | `apps/identity/adapters.py`, `views.OidcCompleteView` | `apps/identity/saml/` |
| Endpoints | `/accounts/oidc/login/…` → `/api/auth/oidc/complete` | `/api/auth/saml/<tenant>/{metadata,login,acs}` |
| Tenant resolution | `?tenant=<slug>` / session hint / default slug | the `<tenant>` slug in the URL |
| User binding | existing active user by verified email, **no JIT** | existing active user by email/NameID, **no JIT** |
| Role | provisioned DB role | DB role, optionally synced from an IdP attribute |
| Proof | `apps/identity/tests/test_oidc.py` | `apps/identity/tests/test_saml.py` |

A **real production IdP (Okta / Azure AD / Google Workspace / ADFS) is the customer's
to provide** — see "What a real IdP needs" at the bottom. Everything here is proven
against a self-signed mock IdP with a real signed-assertion round-trip.

---

## OIDC / OAuth

Wired through allauth's generic `openid_connect` provider, configured from env
(`config/settings/base.py` → `SOCIALACCOUNT_PROVIDERS`):

```
OIDC_PROVIDER_ID, OIDC_PROVIDER_NAME, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET,
OIDC_SERVER_URL, OIDC_DEFAULT_TENANT_SLUG
```

`OIDC_CLIENT_SECRET` is read from the environment — never committed.

**Flow.** Browser → `/accounts/oidc/login/?tenant=<slug>` → IdP login → allauth
callback → `TenantSocialAccountAdapter.pre_social_login` resolves the tenant and binds
the verified identity to an existing active user in that tenant → `LOGIN_REDIRECT_URL`
= `/api/auth/oidc/complete`, which mints the tenant-scoped JWT for the SPA.

**Security posture** (`TenantSocialAccountAdapter`):
- `is_open_for_signup = False` — the IdP authenticates; **it never provisions accounts**.
- The `email_verified` claim is **required** — an unverified email is denied before the
  user lookup (an IdP asserting an arbitrary unverified email can't take over an account).
- The user is resolved **inside the tenant's context**; an identity with no active user
  in the resolved tenant is denied (403). A same-email user in a *different* tenant is
  never matched — proven by `test_adapter_does_not_cross_tenant`.

---

## SAML 2.0 (Service Provider)

We are the **SP**; the tenant's IdP issues signed assertions. `python3-saml` is an SP
*toolkit* — it parses + cryptographically validates the assertion and hands back the
attributes; our code does tenant resolution, user binding, role mapping, and JWT
issuance (see DECISIONS D25 for why this over djangosaml2).

### Per-tenant configuration — `SamlIdpConfig` (one row per tenant)

| Field | Meaning | Secret? |
|---|---|---|
| `enabled` | SAML on/off for the tenant | no |
| `idp_entity_id` | the IdP's entity id / issuer | no |
| `idp_sso_url` | the IdP SSO (redirect) URL | no |
| `idp_x509_cert` | the IdP **signing certificate** (base64 body or PEM) | no — a cert is public |
| `email_attribute` | assertion attribute holding the email (falls back to NameID) | no |
| `role_attribute` | assertion attribute holding the IdP role/group | no |
| `role_map` | `{ "<idp value>": "<our Role>" }` — **empty = no IdP roles** | no |
| `sp_private_key_secret_ref` | **name of the env var** holding the SP private key PEM | the key is, the name isn't |

**No secret is ever stored in the DB or committed.** The IdP cert is public. The only
SP-side secret — a private key, needed *only* if a tenant's IdP requires signed
AuthnRequests or encrypted assertions — is referenced by env-var **name**
(`sp_private_key_secret_ref`) and resolved at runtime (`saml/settings.py
resolve_sp_private_key`). The default SP requires neither, so no key is needed.

### Endpoints (per tenant, by slug)

- `GET  /api/auth/saml/<tenant>/metadata` — SP metadata XML to hand to the IdP admin
  (contains the SP entity id + ACS URL).
- `GET  /api/auth/saml/<tenant>/login` — SP-initiated: 302-redirects the browser to the
  IdP with an AuthnRequest.
- `POST /api/auth/saml/<tenant>/acs` — Assertion Consumer Service: validates the signed
  assertion, then mints the tenant-scoped JWT (`{access, refresh, tenant_id, role}`).

### What is enforced (`saml/settings.py` + `saml/service.py`)

- **Signature required.** `wantAssertionsSigned` + `strict` are forced on; the signature
  is verified against **that tenant's** configured IdP cert. Unsigned and tampered
  assertions are rejected (`test_saml_rejects_unsigned_assertion`,
  `…_tampered_assertion`).
- **Expiry / conditions.** `strict` enforces `NotBefore`/`NotOnOrAfter`, the audience
  (our SP entity id) and the destination (our ACS URL). Expired assertions are rejected
  (`…_rejects_expired_assertion`). SHA-256 is required on signature + digest.
- **Replay.** Each assertion id is consumable once per tenant within the validity window
  (Redis `cache.add`, atomic SET-NX). A re-presented assertion → 401 `saml_replay`
  (`…_rejects_replayed_assertion`, also proven live).
- **Tenant isolation — three independent locks.** (1) the ACS URL is per-tenant; (2) the
  signature is verified against that tenant's cert, so tenant A's IdP can't produce an
  assertion that validates at tenant B's ACS; (3) the user is bound only inside
  `tenant_context(tenant)`, with no JIT. Proven by
  `test_saml_tenant_isolation_idp_a_cannot_mint_tenant_b_session`.
- **Attribute → user/role mapping (capped — no privilege escalation).** Email comes
  from `email_attribute` (or NameID) and must match an **existing active** user in the
  tenant (no JIT — unknown identity → 401 `saml_unknown_user`). The role attribute is
  mapped through the tenant's `role_map`. Because RBAC is enforced on the **DB** role, a
  configured mapping **JIT-syncs** the user's role and writes an immutable
  `identity.saml.role_synced` audit row, so the mapping actually takes effect — **but a
  rank cap means SSO can never raise a role ABOVE the admin-provisioned one.** A mapped
  role that outranks the current role is refused and clamped (logged, no change); a
  mapped role at or below it is applied (de-escalation persists, so the provisioned role
  is also the ceiling for any later mapping — only an admin re-provisioning raises a
  role). With an **empty `role_map` (the default)** nothing is synced — the Hub stays
  authoritative, exactly like OIDC. Tests: `test_saml_role_mapping_cannot_escalate_above_provisioned`,
  `…_can_deescalate_and_audits`, `…_falls_back_to_db_role_when_attribute_absent`.

### Setting up a tenant (admin runbook)

1. Create/enable a `SamlIdpConfig` for the tenant with the IdP's entity id, SSO URL and
   signing certificate (and, if needed, the attribute names + `role_map`).
2. Give the IdP admin the SP metadata: `GET /api/auth/saml/<tenant>/metadata`. Register
   that SP in the IdP (entity id + ACS URL come straight from the metadata).
3. In the IdP, release `email` (or set the NameID to the email) and, if using role sync,
   the role/group attribute named in `role_attribute`.
4. Test: `GET /api/auth/saml/<tenant>/login` → IdP → back to the ACS → you receive
   `{access, refresh}`. Use the access token as `Authorization: Bearer …`.

---

## Proof status

- **[test]** `test_oidc.py` (9) + `test_saml.py` (12) — green in the 1185-test suite.
  SAML uses a self-signed mock IdP and a **real xmlsec-signed** assertion (happy path,
  tamper, unsigned, expiry, replay, cross-tenant isolation, role sync + fallback,
  metadata, login redirect, not-configured 404).
- **[live]** Against the running gunicorn stack: metadata `200`; a signed ACS round-trip
  → `200` with the mapped role + correct tenant; `/me` with the SSO-minted JWT → `200`;
  a replay of the same assertion → `401 saml_replay`.

## 🔑 What a real production IdP needs (customer's responsibility)

- A real IdP application in **Okta / Azure AD / Google Workspace / ADFS** per tenant,
  with our SP registered (entity id + ACS URL from the metadata endpoint), the IdP
  signing certificate pasted into `idp_x509_cert`, and the email (+ optional role/group)
  attribute released.
- **TLS 1.2+** terminating in front of the ACS (SAML POST must be over HTTPS in prod).
- If the IdP mandates signed AuthnRequests or encrypted assertions: generate an SP
  keypair, register the SP cert at the IdP, and set `sp_private_key_secret_ref` to the
  env var holding the private key (the key itself is provisioned as a secret, never in
  the repo/DB).
- The OIDC client secret (`OIDC_CLIENT_SECRET`) and any production IdP credentials are
  provisioned via the environment.
