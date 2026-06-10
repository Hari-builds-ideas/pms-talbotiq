"""
The management-only access gate for succession (the SENSITIVITY rule).

Succession holds the most sensitive data in the system. There is NO employee
access to ANY succession endpoint — not even to their own 9-box or readiness. An
employee (or any non-management role) hitting any succession endpoint gets a 404,
NOT a 403: the module must not leak its own existence.

``SuccessionParticipant`` enforces that and is ordered BEFORE the capability check
so an employee 404s before ``HasCapability`` could 403 them. Managers / HRBP /
Admin pass this gate and are then (a) gated by the specific capability — a Manager
hitting an HRBP-only action (critical-role registry, generate, publish) gets the
usual 403 — and (b) scope-bounded by the services (an out-of-tier target → 404).
"""
from rest_framework.exceptions import NotFound
from rest_framework.permissions import BasePermission, IsAuthenticated

from apps.rbac.matrix import Role
from apps.rbac.mixins import RBACMixin
from apps.rbac.permissions import HasCapability


class SuccessionParticipant(BasePermission):
    """Pass only MANAGER / HRBP / ADMIN; everyone else (employees, unknown roles)
    gets a 404 so the module is invisible to them."""

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False  # IsAuthenticated handles the 401; this is defence in depth
        if user.role not in (Role.MANAGER, Role.HRBP, Role.ADMIN):
            raise NotFound("Not found.")
        return True


class SuccessionMixin(RBACMixin):
    """RBACMixin + the management-only 404 gate.

    Builds the permission stack as ``[IsAuthenticated, SuccessionParticipant,
    HasCapability]`` — the participant gate runs before the capability check so an
    employee 404s rather than 403s. Object scope is enforced in the services
    (which raise 404 for out-of-tier targets), so ``WithinScope`` is not used here.
    """

    def get_permissions(self):
        return [IsAuthenticated(), SuccessionParticipant(), HasCapability()]
