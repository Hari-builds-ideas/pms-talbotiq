"""
Integration-config API (Admin-only) — the only USER surface of Module 12. The
syncs (Jira) and sends (Slack) are system-driven (signals / Celery), not endpoints.

Views are THIN and the SOLE RBAC gate (``MANAGE_INTEGRATIONS`` — Admin). The
services own the audited writes; the tenant is bound from the JWT, so the
tenant-scoped manager confines every read/write to the caller's tenant. NO secret
value is ever accepted or returned — only the non-secret config + the env-var NAME
(``secret_ref``); see ``secrets.py`` + ``NEEDS_HARI_secrets.md``.
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.rbac.matrix import Capability
from apps.rbac.mixins import RBACMixin

from . import services
from .models import TenantIntegration
from .serializers import IntegrationUpsertSerializer, TenantIntegrationSerializer


class IntegrationListView(RBACMixin, APIView):
    """``GET /api/integrations`` (MANAGE_INTEGRATIONS — Admin) — the tenant's
    configured integrations (both kinds)."""

    required_capability = Capability.MANAGE_INTEGRATIONS

    def get(self, request):
        integrations = services.list_integrations(request.user)
        return Response(TenantIntegrationSerializer(integrations, many=True).data)


class IntegrationDetailView(RBACMixin, APIView):
    """``GET, PUT /api/integrations/<kind>`` (MANAGE_INTEGRATIONS — Admin).

    GET: the tenant's integration of that kind (404 if not configured yet). PUT:
    upsert enabled / non-secret config / secret_ref (an env-var NAME). An unknown
    kind / non-object config → 422; a raw token is never accepted."""

    required_capability = Capability.MANAGE_INTEGRATIONS

    def get(self, request, kind):
        kind = kind.upper()
        integration = services.get_integration(request.user, kind)
        if integration is None:
            return Response(
                {"detail": f"No {kind} integration configured."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(TenantIntegrationSerializer(integration).data)

    def put(self, request, kind):
        kind = kind.upper()
        serializer = IntegrationUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        integration = services.upsert_integration(
            request.user,
            kind,
            enabled=data["enabled"],
            config=data.get("config") or {},
            secret_ref=data.get("secret_ref") or "",
        )
        return Response(TenantIntegrationSerializer(integration).data)
