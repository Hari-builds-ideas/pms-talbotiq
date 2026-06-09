"""
Test-only urlconf, activated per-test via
``@pytest.mark.urls("apps.billing.tests.urls")``.

Not referenced by the production ``config.urls`` — exists solely to mount the
entitlement-gate probe view.
"""
from django.urls import path

from .views import Agent3ProbeView

urlpatterns = [
    path("billing-test/agent3/", Agent3ProbeView.as_view(), name="billing-test-agent3"),
]
