"""
Test-only DRF view exercising the real RBAC permission stack end-to-end.

This lives under ``tests/`` and is wired only by ``tests/urls.py`` behind
``@pytest.mark.urls`` — it is never part of the production urlconf. It proves
that :class:`~apps.rbac.mixins.RBACMixin` + the permission classes integrate
over real HTTP with JWT auth and tenant binding by ``TenantMiddleware``.

``GET /rbac-test/users/<uuid>/`` returns the target user's email iff the caller
holds ``view_team_analytics`` AND the target is within the caller's data scope;
otherwise the permission stack yields 403 (401 if unauthenticated).
"""
from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identity.models import User
from apps.rbac.matrix import Capability
from apps.rbac.mixins import RBACMixin


class ScopedUserDetailView(RBACMixin, APIView):
    """Read one user, gated by capability + data scope.

    ``required_capability`` is ``view_team_analytics`` (Manager/HRBP/Admin), and
    ``enforce_object_scope`` turns on object-level scoping where the object IS
    the subject user. The target is fetched through the tenant-scoped manager —
    ``TenantMiddleware`` has already bound the tenant from the verified JWT, so a
    cross-tenant id simply resolves to ``None`` (404) and never leaks.
    """

    required_capability = Capability.VIEW_TEAM_ANALYTICS
    enforce_object_scope = True

    def get(self, request, user_id):
        target = User.objects.filter(pk=user_id).first()
        if target is None:
            return Response({"detail": "Not found."}, status=404)
        # Imperative scope enforcement (this view doesn't use get_object()).
        self.check_object_scope(target)
        return Response({"email": target.email})
