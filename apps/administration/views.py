"""
The Admin Hub API — the HTTP surface of Module 11's administration app, mounted
under ``/api/admin/``. EVERY endpoint is Admin-only.

Views stay THIN and are the SOLE RBAC gate: each declares its
``required_capability`` (or, for a multi-method view, a ``_caps`` map + a
``get_permissions`` override). The ``services`` are the SOLE mutators and the SOLE
audit writers — the views only gate the capability, validate the body shape,
resolve referenced users through the tenant-scoped ``User.objects`` manager (a
cross-tenant id → 404), call the service, and serialize.

Everything that could be spoofed is server-set: the actor is ``request.user`` and
the tenant is ``request.user.tenant`` (bound from the verified JWT by
``TenantMiddleware``) — never accepted from the client. Service exceptions
propagate to DRF automatically: an unknown role / duplicate email → 422
(``InvalidAdminInput``); a reporting cycle → 422 (``ReportingCycle``); a
cross-tenant referenced id → 404 (``get_object_or_404`` over the scoped manager).
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identity.models import User
from apps.rbac.matrix import Capability
from apps.rbac.mixins import RBACMixin

from . import services
from .serializers import (
    CreateUserSerializer,
    DisplayNameSerializer,
    ReportingLineSerializer,
    SetRoleSerializer,
    TenantConfigSerializer,
    UserAdminSerializer,
)


# ── users / roles ──────────────────────────────────────────────────────────────


class UserListCreateView(RBACMixin, APIView):
    """``GET, POST /api/admin/users`` (MANAGE_USERS_ROLES — Admin).

    GET: every user in the actor's tenant. POST: create a user; the optional
    ``manager`` UUID is resolved through the tenant-scoped manager (cross-tenant
    id → 404). A duplicate email or unknown role → 422.
    """

    _caps = {"GET": Capability.MANAGE_USERS_ROLES, "POST": Capability.MANAGE_USERS_ROLES}

    def get_permissions(self):
        self.required_capability = self._caps.get(self.request.method)
        return super().get_permissions()

    def get(self, request):
        users = services.list_users(request.user)
        return Response(UserAdminSerializer(users, many=True).data)

    def post(self, request):
        serializer = CreateUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        manager = None
        if data.get("manager") is not None:
            manager = get_object_or_404(User.objects.all(), pk=data["manager"])
        user = services.create_user(
            request.user,
            email=data["email"],
            role=data["role"],
            manager=manager,
            password=data.get("password"),
            display_name=data.get("display_name"),
        )
        return Response(
            UserAdminSerializer(user).data, status=status.HTTP_201_CREATED
        )


class UserStatsView(RBACMixin, APIView):
    """``GET /api/admin/users/stats`` (MANAGE_USERS_ROLES — Admin) — tenant user
    counts (active/inactive totals + active-by-role), aggregated in the DB so the
    dashboard never downloads the whole user list just to count it."""

    required_capability = Capability.MANAGE_USERS_ROLES

    def get(self, request):
        return Response(services.user_stats(request.user))


class UserRoleView(RBACMixin, APIView):
    """``POST /api/admin/users/<pk>/role`` (MANAGE_USERS_ROLES — Admin) — assign a
    role. The target user is resolved through the tenant-scoped manager
    (cross-tenant id → 404); an unknown role → 422."""

    required_capability = Capability.MANAGE_USERS_ROLES

    def post(self, request, pk):
        user = get_object_or_404(User.objects.all(), pk=pk)
        serializer = SetRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.set_role(request.user, user, serializer.validated_data["role"])
        return Response(UserAdminSerializer(user).data)


class UserDisplayNameView(RBACMixin, APIView):
    """``POST /api/admin/users/<pk>/display-name`` (MANAGE_USERS_ROLES — Admin) —
    set/clear a user's display name. Blank/null clears it (→ email fallback)."""

    required_capability = Capability.MANAGE_USERS_ROLES

    def post(self, request, pk):
        user = get_object_or_404(User.objects.all(), pk=pk)
        serializer = DisplayNameSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.set_display_name(
            request.user, user, serializer.validated_data["display_name"]
        )
        return Response(UserAdminSerializer(user).data)


class UserDeactivateView(RBACMixin, APIView):
    """``POST /api/admin/users/<pk>/deactivate`` (MANAGE_USERS_ROLES — Admin) — set
    the user inactive. The target is resolved through the tenant-scoped manager
    (cross-tenant id → 404)."""

    required_capability = Capability.MANAGE_USERS_ROLES

    def post(self, request, pk):
        user = get_object_or_404(User.objects.all(), pk=pk)
        user = services.set_active(request.user, user, is_active=False)
        return Response(UserAdminSerializer(user).data)


class UserReactivateView(RBACMixin, APIView):
    """``POST /api/admin/users/<pk>/reactivate`` (MANAGE_USERS_ROLES — Admin) — set
    the user active. The target is resolved through the tenant-scoped manager
    (cross-tenant id → 404)."""

    required_capability = Capability.MANAGE_USERS_ROLES

    def post(self, request, pk):
        user = get_object_or_404(User.objects.all(), pk=pk)
        user = services.set_active(request.user, user, is_active=True)
        return Response(UserAdminSerializer(user).data)


class UserReportingLineView(RBACMixin, APIView):
    """``POST /api/admin/users/<pk>/reporting-line`` (MANAGE_USERS_ROLES — Admin) —
    reassign the user's manager. Both the user and the new ``manager`` are resolved
    through the tenant-scoped manager (cross-tenant id → 404). A cycle → 422
    (``ReportingCycle``, raised by the reused Module-7 reassignment)."""

    required_capability = Capability.MANAGE_USERS_ROLES

    def post(self, request, pk):
        user = get_object_or_404(User.objects.all(), pk=pk)
        serializer = ReportingLineSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_manager = get_object_or_404(
            User.objects.all(), pk=serializer.validated_data["manager"]
        )
        user = services.set_reporting_line(request.user, user, new_manager)
        return Response(UserAdminSerializer(user).data)


# ── tenant config ────────────────────────────────────────────────────────────


class TenantConfigView(RBACMixin, APIView):
    """``GET, PUT /api/admin/tenant-config`` (MANAGE_TENANT_CONFIG — Admin).

    GET: the tenant's config (creating an empty row on first access). PUT: replace
    the ``settings`` bag (a JSON object); a non-object → 422 in the service.
    """

    _caps = {
        "GET": Capability.MANAGE_TENANT_CONFIG,
        "PUT": Capability.MANAGE_TENANT_CONFIG,
    }

    def get_permissions(self):
        self.required_capability = self._caps.get(self.request.method)
        return super().get_permissions()

    def get(self, request):
        config = services.get_tenant_config(request.user)
        return Response(TenantConfigSerializer(config).data)

    def put(self, request):
        config = services.update_tenant_config(
            request.user, settings=request.data.get("settings", {})
        )
        return Response(TenantConfigSerializer(config).data)
