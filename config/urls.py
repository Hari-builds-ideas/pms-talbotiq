from django.urls import include, path

urlpatterns = [
    # Liveness / ops
    path("", include("apps.core.urls")),
    # Module 1 — Identity & auth
    path("api/auth/", include("apps.identity.urls")),
    # Module 13 — Admin & Billing entitlements
    path("api/billing/", include("apps.billing.urls")),
    # Module 2 — Goals & KPI engine
    path("api/cycles/", include("apps.cycles.urls")),
    path("api/goals/", include("apps.goals.urls")),
    # Module 3 — Reviews & Appraisal Cycles
    path("api/reviews/", include("apps.reviews.urls")),
    # Module 4 — 360° Feedback & anonymisation
    path("api/feedback/", include("apps.feedback.urls")),
    # Module 5 — Approval Workflows
    path("api/approvals/", include("apps.approvals.urls")),
    # OAuth / OIDC login + callback (django-allauth)
    path("accounts/", include("allauth.urls")),
]
