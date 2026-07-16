"""
Billing routes, mounted under ``/api/billing/`` by the root urlconf.

Paths are declared WITHOUT a leading slash because they are appended to the
``api/billing/`` mount point. All endpoints are admin-only (see ``views.py``).
"""
from django.urls import path

from .views import (
    CheckoutView,
    EntitlementView,
    FeatureFlagsView,
    InvoiceListView,
    MyFeaturesView,
    PaymentsConfigView,
    RazorpayWebhookView,
    SeatsView,
    StripeWebhookView,
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
    # ─── PROD_C — payments (Stripe + Razorpay, TEST MODE) ───
    path("payments-config", PaymentsConfigView.as_view(), name="payments-config"),
    path("checkout", CheckoutView.as_view(), name="checkout"),
    path("invoices", InvoiceListView.as_view(), name="invoices"),
    # Webhooks are PUBLIC but signature-verified (the trust boundary).
    path("webhooks/stripe", StripeWebhookView.as_view(), name="webhook-stripe"),
    path("webhooks/razorpay", RazorpayWebhookView.as_view(), name="webhook-razorpay"),
]
