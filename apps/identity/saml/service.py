"""
SAML assertion processing: validate (signature + strict conditions + expiry),
guard against replay, map attributes → an existing tenant user + role.

Security posture mirrors the OIDC adapter exactly — no JIT provisioning, deny
unknown identities, never cross the tenant boundary — and terminates in the same
JWT issuance. python3-saml does the cryptographic validation (signature against
the tenant's configured IdP cert, NotBefore/NotOnOrAfter, audience, destination);
this layer adds the tenant-scoped user binding, the role mapping, and a replay
guard over the assertion id. See DECISIONS D25.
"""
import logging

from django.core.cache import cache
from onelogin.saml2.auth import OneLogin_Saml2_Auth

from apps.audit.services import record as audit_record
from apps.tenancy.context import tenant_context

from ..models import SamlIdpConfig, User  # noqa: F401  (SamlIdpConfig kept for callers)
from .settings import build_saml_settings, prepare_django_request

logger = logging.getLogger("pms.identity")

# Reject a re-presented assertion id seen within this window. Comfortably covers a
# typical assertion validity (a few minutes) without unbounded cache growth.
REPLAY_TTL_SECONDS = 10 * 60


class SamlAuthError(Exception):
    """A SAML response failed validation or could not be mapped to a tenant user."""

    def __init__(self, message, code="saml_invalid"):
        super().__init__(message)
        self.code = code


def _map_role(config, attributes, fallback_role):
    """Map the IdP role/group attribute through the tenant's ``role_map`` → a Role.

    An empty role_map (the default) means the tenant did NOT opt into IdP-driven
    roles → the provisioned DB role always wins (same posture as OIDC). When a map
    is set, the first asserted value that maps to a known Role is used; an
    absent/unknown value falls back to the DB role (never escalate on missing data).
    """
    attr = (config.role_attribute or "").strip()
    role_map = config.role_map or {}
    if not attr or not role_map:
        return fallback_role
    for value in attributes.get(attr, []) or []:
        mapped = role_map.get(value)
        if mapped in User.Role.values:
            return mapped
    return fallback_role


def _resolve_and_sync_role(config, attributes, user):
    """Map the IdP attribute → a Role and JIT-sync it onto the pre-provisioned user.

    RBAC is enforced server-side on the user's **DB** role (not the token claim),
    so for the mapping to actually take effect the resolved role is persisted onto
    the user record and the change is audited. This only ever fires when the tenant
    configured a ``role_map`` (an explicit opt-in to IdP-authoritative roles); with
    no map the resolved role equals the current role and nothing is written — i.e.
    the Hub stays authoritative, exactly like OIDC. Must run inside ``tenant_context``.
    """
    resolved = _map_role(config, attributes, user.role)
    if resolved != user.role:
        previous = user.role
        user.role = resolved
        user.save(update_fields=["role", "updated_at"])
        audit_record(
            action="identity.saml.role_synced",
            actor=user,
            target_type="User",
            target_id=user.id,
            metadata={"from": previous, "to": resolved, "source": "saml"},
        )
    return user.role


def _extract_email(config, auth) -> str:
    """Email from the configured attribute, falling back to the NameID."""
    attr = (config.email_attribute or "").strip()
    if attr:
        values = auth.get_attribute(attr) or []
        if values and values[0]:
            return values[0].strip().lower()
    return (auth.get_nameid() or "").strip().lower()


def process_saml_response(tenant, config, request):
    """Validate the POSTed SAML Response for ``tenant`` → (user, session_role).

    Raises ``SamlAuthError`` on any validation, replay, or mapping failure.
    """
    auth = OneLogin_Saml2_Auth(
        prepare_django_request(request),
        old_settings=build_saml_settings(config, request, tenant.slug),
    )
    auth.process_response()

    errors = auth.get_errors()
    if errors:
        reason = auth.get_last_error_reason() or ""
        raise SamlAuthError(f"SAML validation failed: {errors} {reason}".strip())
    if not auth.is_authenticated():
        raise SamlAuthError("SAML response is not authenticated.")

    # Replay guard: a given assertion id may be consumed once per tenant within the
    # validity window. cache.add is an atomic SET-NX on the Redis backend.
    assertion_id = auth.get_last_assertion_id()
    if assertion_id:
        replay_key = f"saml:replay:{tenant.id}:{assertion_id}"
        if not cache.add(replay_key, "1", REPLAY_TTL_SECONDS):
            raise SamlAuthError("SAML assertion replay detected.", code="saml_replay")

    email = _extract_email(config, auth)
    if not email:
        raise SamlAuthError("SAML response carried no email/NameID.")

    # Tenant binding: resolve + map ONLY inside this tenant's context. No JIT — an
    # identity with no active user in THIS tenant is denied (mirrors OIDC). This is
    # the lock that stops tenant A's IdP minting a tenant B session.
    with tenant_context(tenant):
        user = User.objects.filter(email=email, is_active=True).first()
        if user is None:
            raise SamlAuthError(
                "No active user for this identity in the resolved tenant.",
                code="saml_unknown_user",
            )
        role = _resolve_and_sync_role(config, auth.get_attributes(), user)
    return user, role
