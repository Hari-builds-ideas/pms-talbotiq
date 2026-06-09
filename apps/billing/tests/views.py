"""
Test-only DRF view exercising the entitlement gate end-to-end.

Mounted solely by ``apps.billing.tests.urls`` behind ``@pytest.mark.urls`` — it
is never part of the production urlconf. ``GET /billing-test/agent3/`` is guarded
by ``requires_entitlement("agent3")``, so it returns 200 only when the caller's
tenant holds a pack unlocking agent3 (i.e. after a FULL_AI upgrade), and 403
otherwise.
"""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.gate import requires_entitlement


class Agent3ProbeView(APIView):
    """Trivial view behind the agent3 entitlement gate."""

    permission_classes = [IsAuthenticated, requires_entitlement("agent3")]

    def get(self, request):
        return Response({"ran": "agent3"})
