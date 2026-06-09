"""
Billing & entitlements endpoints (admin-only).

Every endpoint here is gated by :class:`~apps.rbac.mixins.RBACMixin` with
``Capability.MANAGE_TENANT`` — the ADMIN-only capability covering tenant config,
users, roles and billing/entitlements. Non-admins get 403; unauthenticated
requests get 401.

The tenant is resolved from ``request.user.tenant`` (``TenantMiddleware`` has
bound the same tenant from the verified JWT, so the scoped reads inside the
services line up). All mutation logic lives in ``services.py``; the views are
thin and only translate HTTP <-> service calls.
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.rbac.matrix import Capability
from apps.rbac.mixins import RBACMixin

from .serializers import EntitlementSerializer
from .services import get_entitlement_cached, set_seats, upgrade_to_full_ai


class EntitlementView(RBACMixin, APIView):
    """``GET /api/billing/entitlement`` — the caller's tenant entitlement.

    Returns the current entitlement, provisioning a STARTER default on first
    access so a freshly created tenant always reads a sane row.
    """

    required_capability = Capability.MANAGE_TENANT

    def get(self, request):
        entitlement = get_entitlement_cached(request.user.tenant)
        return Response(EntitlementSerializer(entitlement).data)


class UpgradeView(RBACMixin, APIView):
    """``POST /api/billing/upgrade`` — add the FULL_AI pack (unlock agents 3-5).

    Idempotent and seat-preserving: only ``feature_packs`` changes. Returns the
    updated entitlement, whose ``unlocked_agents`` now include agents 3-5.
    """

    required_capability = Capability.MANAGE_TENANT

    def post(self, request):
        entitlement = upgrade_to_full_ai(request.user.tenant, actor=request.user)
        return Response(EntitlementSerializer(entitlement).data)


class SeatsView(RBACMixin, APIView):
    """``PATCH /api/billing/seats`` — set seat_count independently of packs.

    Body: ``{"seat_count": N}`` (a non-negative integer). Demonstrates that
    seats move without touching feature packs.
    """

    required_capability = Capability.MANAGE_TENANT

    def patch(self, request):
        raw = request.data.get("seat_count")
        try:
            seat_count = int(raw)
        except (TypeError, ValueError):
            return Response(
                {"detail": "seat_count must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if seat_count < 0:
            return Response(
                {"detail": "seat_count must be non-negative."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        entitlement = set_seats(request.user.tenant, seat_count, actor=request.user)
        return Response(EntitlementSerializer(entitlement).data)
