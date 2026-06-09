from django.urls import include, path

urlpatterns = [
    # Liveness / ops
    path("", include("apps.core.urls")),
    # Module 1 — Identity & auth
    path("api/auth/", include("apps.identity.urls")),
    # Module 13 — Admin & Billing entitlements
    path("api/billing/", include("apps.billing.urls")),
    # OAuth / OIDC login + callback (django-allauth)
    path("accounts/", include("allauth.urls")),
]
