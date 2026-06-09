"""
JWT issuance. Every token carries the tenant_id + role claims that
TenantMiddleware and the RBAC layer rely on. Claims are stamped on the refresh
token; simplejwt's ``RefreshToken.access_token`` copies them onto the access
token (and onto refreshed access tokens), so isolation survives token rotation.
"""
from rest_framework_simplejwt.tokens import RefreshToken


def _stamp_claims(token, user):
    token["tenant_id"] = str(user.tenant_id)
    token["role"] = user.role
    token["email"] = user.email


def issue_tokens_for_user(user):
    """Return (access_str, refresh_str) for a tenant-scoped session."""
    refresh = RefreshToken.for_user(user)
    _stamp_claims(refresh, user)
    access = refresh.access_token
    _stamp_claims(access, user)
    return str(access), str(refresh)
