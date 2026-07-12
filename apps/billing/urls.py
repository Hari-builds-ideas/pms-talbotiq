"""
Billing routes, mounted under ``/api/billing/`` by the root urlconf.

Paths are declared WITHOUT a leading slash because they are appended to the
``api/billing/`` mount point. All endpoints are admin-only (see ``views.py``).
"""
from django.urls import path

from .views import (
    EntitlementView,
    FeatureFlagsView,
    MyFeaturesView,
    SeatsView,
    SubscriptionView,
    UpgradePromptView,
    UpgradeView,
)

app_name = "billing"

urlpatterns = [
    path("entitlement", EntitlementView.as_view(), name="entitlement"),
    path("upgrade", UpgradeView.as_view(), name="upgrade"),
    path("seats", SeatsView.as_view(), name="seats"),
    path("feature-flags", FeatureFlagsView.as_view(), name="feature-flags"),
    path("my-features", MyFeaturesView.as_view(), name="my-features"),
    path("upgrade-prompt", UpgradePromptView.as_view(), name="upgrade-prompt"),
    # ─── PHASE2 L1.4 — the internal subscription (plan + lifecycle; no gateway) ───
    path("subscription", SubscriptionView.as_view(), name="subscription"),
]
