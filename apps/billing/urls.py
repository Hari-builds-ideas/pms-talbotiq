"""
Billing routes, mounted under ``/api/billing/`` by the root urlconf.

Paths are declared WITHOUT a leading slash because they are appended to the
``api/billing/`` mount point. All endpoints are admin-only (see ``views.py``).
"""
from django.urls import path

from .views import EntitlementView, SeatsView, UpgradeView

app_name = "billing"

urlpatterns = [
    path("entitlement", EntitlementView.as_view(), name="entitlement"),
    path("upgrade", UpgradeView.as_view(), name="upgrade"),
    path("seats", SeatsView.as_view(), name="seats"),
]
