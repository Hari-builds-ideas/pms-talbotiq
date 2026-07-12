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
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.rbac.matrix import Capability
from apps.rbac.mixins import RBACMixin

from .serializers import EntitlementSerializer
from .services import (
    InvalidSubscriptionTransition,
    feature_flags_for,
    get_entitlement_cached,
    get_or_create_subscription,
    set_plan,
    set_seats,
    set_subscription_status,
    upgrade_prompt,
    upgrade_to_full_ai,
)


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


class FeatureFlagsView(RBACMixin, APIView):
    """``GET /api/billing/feature-flags`` (MANAGE_ENTITLEMENTS) — the tenant's
    complete ``{feature: bool}`` flag map, derived from its entitlement packs.

    A STARTER tenant reads agents 3-5 (and the paid generative seams) as ``False``;
    a FULL_AI tenant reads them ``True``. The map is the single source the frontend
    gates UI on; the upgrade switch flips it instantly (the cache is cleared on any
    entitlement change).
    """

    required_capability = Capability.MANAGE_ENTITLEMENTS

    def get(self, request):
        return Response(feature_flags_for(request.user.tenant))


class UpgradePromptView(RBACMixin, APIView):
    """``GET /api/billing/upgrade-prompt`` (MANAGE_ENTITLEMENTS) — data for an
    in-app upgrade prompt: the current packs/flags, the features still LOCKED, and
    what unlocking with FULL_AI would add. Conceptual only — no pricing/payment
    (Phase 2)."""

    required_capability = Capability.MANAGE_ENTITLEMENTS

    def get(self, request):
        return Response(upgrade_prompt(request.user.tenant))


class MyFeaturesView(APIView):
    """``GET /api/billing/my-features`` — the CALLER's own tenant feature-flag map
    ``{feature: bool}``, readable by ANY authenticated role (not Admin-only, unlike
    ``/feature-flags``). Same data as ``feature_flags_for`` — so any UI (employee,
    manager, HRBP, admin) can pre-disable locked premium controls instead of
    discovering them via 403/503.

    It exposes ONLY the caller's own tenant flags (the tenant is bound from the JWT;
    a caller can never read another tenant's map). No capability is required beyond
    authentication — the map is not sensitive, it just reflects what the tenant has
    paid for.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(feature_flags_for(request.user.tenant))


class SubscriptionView(RBACMixin, APIView):
    """``GET, PATCH /api/billing/subscription`` (MANAGE_TENANT — Admin).

    PHASE2 L1.4 — the INTERNAL subscription: an admin sets the tenant's plan
    and/or lifecycle status; the entitlement packs sync from the plan catalogue
    and access flips immediately. No payment gateway (that's the human-reviewed
    payments lane)."""

    required_capability = Capability.MANAGE_TENANT

    @staticmethod
    def _payload(subscription):
        from .packs import PLAN_CATALOG

        catalog = PLAN_CATALOG.get(subscription.plan, {})
        return {
            "plan": subscription.plan,
            "status": subscription.status,
            "features_active": subscription.features_active,
            "employee_limit": catalog.get("employee_limit", 0),
            "plan_features": sorted(catalog.get("features", ())),
            "packs": list(catalog.get("packs", ())),
            "trial_ends_at": subscription.trial_ends_at,
            "current_period_end": subscription.current_period_end,
            "plans": {
                code: {
                    "label": c["label"],
                    "employee_limit": c["employee_limit"],
                    "features": sorted(c["features"]),
                }
                for code, c in PLAN_CATALOG.items()
            },
        }

    def get(self, request):
        return Response(self._payload(get_or_create_subscription(request.user.tenant_id)))

    def patch(self, request):
        subscription = get_or_create_subscription(request.user.tenant_id)
        plan = request.data.get("plan")
        new_status = request.data.get("status")
        try:
            if plan and plan != subscription.plan:
                subscription = set_plan(request.user.tenant_id, plan, actor=request.user)
            if new_status and new_status != subscription.status:
                subscription = set_subscription_status(
                    request.user.tenant_id, new_status, actor=request.user
                )
        except ValueError as exc:
            return Response({"plan": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
        except InvalidSubscriptionTransition as exc:
            return Response({"status": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self._payload(subscription))
