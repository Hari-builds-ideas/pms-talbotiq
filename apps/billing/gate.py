"""
The entitlement gate — the API-level feature flag.

The spec calls for feature flags at the API and UI layers. ``requires_entitlement``
builds a DRF permission class that admits a request only when the caller's tenant
holds a pack unlocking the named agent. This is orthogonal to RBAC: RBAC answers
"is your *role* allowed to do this?", the entitlement gate answers "has your
*tenant* paid for this feature?". A view that needs both lists both.

Resolution: the caller's tenant is taken from ``request.user.tenant``;
``TenantMiddleware`` has already bound that tenant from the verified JWT, so the
scoped reads inside ``tenant_has_agent`` line up. Fails closed — an
unauthenticated request, or a tenant whose packs do not unlock the agent, is
denied (DRF turns that into 403, or 401 when unauthenticated).
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission

from .services import tenant_has_agent


def requires_entitlement(agent_code: str) -> type[BasePermission]:
    """Build a permission class that admits only tenants entitled to ``agent_code``.

    Usage::

        class RunAgent3View(APIView):
            permission_classes = [IsAuthenticated, requires_entitlement("agent3")]
    """

    class _RequiresEntitlement(BasePermission):
        message = f"Your plan does not include this feature ({agent_code})."
        _agent_code = agent_code

        def has_permission(self, request, view) -> bool:
            user = getattr(request, "user", None)
            if user is None or not user.is_authenticated:
                return False
            tenant = getattr(user, "tenant", None)
            if tenant is None:
                return False
            return tenant_has_agent(tenant, self._agent_code)

    _RequiresEntitlement.__name__ = f"RequiresEntitlement[{agent_code}]"
    _RequiresEntitlement.__qualname__ = _RequiresEntitlement.__name__
    return _RequiresEntitlement
