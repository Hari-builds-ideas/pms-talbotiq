"""
Test-only urlconf, activated per-test via
``@pytest.mark.urls("apps.core.tests.throttle_urls")``.

Not referenced by the production ``config.urls`` — it exists solely to mount a
trivial authenticated view behind :class:`~apps.core.throttling.TenantThrottle`
so the throttle's 429 can be exercised over a real HTTP request/response cycle
(status code, ``Retry-After`` header, upgrade hint in the body).
"""
from django.urls import path
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.throttling import TenantThrottle


class ThrottledProbeView(APIView):
    """Authenticated no-op guarded by the tenant throttle."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [TenantThrottle]

    def get(self, request):
        return Response({"ran": "probe"})


urlpatterns = [
    path("throttle-test/probe/", ThrottledProbeView.as_view(), name="throttle-test-probe"),
]
