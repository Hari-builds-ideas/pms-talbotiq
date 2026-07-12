"""
JWT issuance. Every token carries the tenant_id + role claims that
TenantMiddleware and the RBAC layer rely on. Claims are stamped on the refresh
token; simplejwt's ``RefreshToken.access_token`` copies them onto the access
token (and onto refreshed access tokens), so isolation survives token rotation.
"""
from rest_framework_simplejwt.tokens import RefreshToken


def _stamp_claims(token, user, role=None, device_id=None):
    token["tenant_id"] = str(user.tenant_id)
    # ``role`` lets SSO map an IdP-asserted role onto the session (SAML role
    # mapping); it defaults to the user's provisioned DB role for every other path.
    token["role"] = role or user.role
    token["email"] = user.email
    if device_id:
        # Device-session id (PHASE2 L1.3). Survives refresh rotation like the
        # claims above; re-checked at refresh so a revoked session can't rotate.
        token["did"] = str(device_id)


def issue_tokens_for_user(user, *, role=None, device_id=None):
    """Return (access_str, refresh_str) for a tenant-scoped session.

    ``role`` overrides the stamped role claim (used by SAML attribute→role
    mapping); when omitted the user's provisioned DB role is used. tenant_id is
    always the user's own tenant — SSO can never change which tenant a session
    belongs to. ``device_id`` ties the token pair to a DeviceSession row so the
    session can be listed and revoked (L1.3).
    """
    refresh = RefreshToken.for_user(user)
    _stamp_claims(refresh, user, role, device_id)
    access = refresh.access_token
    _stamp_claims(access, user, role, device_id)
    return str(access), str(refresh)
