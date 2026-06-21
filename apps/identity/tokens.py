"""
JWT issuance. Every token carries the tenant_id + role claims that
TenantMiddleware and the RBAC layer rely on. Claims are stamped on the refresh
token; simplejwt's ``RefreshToken.access_token`` copies them onto the access
token (and onto refreshed access tokens), so isolation survives token rotation.
"""
from rest_framework_simplejwt.tokens import RefreshToken


def _stamp_claims(token, user, role=None):
    token["tenant_id"] = str(user.tenant_id)
    # ``role`` lets SSO map an IdP-asserted role onto the session (SAML role
    # mapping); it defaults to the user's provisioned DB role for every other path.
    token["role"] = role or user.role
    token["email"] = user.email


def issue_tokens_for_user(user, *, role=None):
    """Return (access_str, refresh_str) for a tenant-scoped session.

    ``role`` overrides the stamped role claim (used by SAML attribute→role
    mapping); when omitted the user's provisioned DB role is used. tenant_id is
    always the user's own tenant — SSO can never change which tenant a session
    belongs to.
    """
    refresh = RefreshToken.for_user(user)
    _stamp_claims(refresh, user, role)
    access = refresh.access_token
    _stamp_claims(access, user, role)
    return str(access), str(refresh)
