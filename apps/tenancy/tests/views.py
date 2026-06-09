"""Test-only probe view: reports the tenant currently bound in the contextvar.

Mounted only via ``tests/urls.py`` behind ``@pytest.mark.urls`` — never part of
the production urlconf. Used to prove the per-request tenant context is set from
the JWT and reset afterwards (no cross-request bleed)."""
from django.http import JsonResponse
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.tenancy.context import get_current_tenant_id


class WhoTenantView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return JsonResponse({"tenant": get_current_tenant_id()})
