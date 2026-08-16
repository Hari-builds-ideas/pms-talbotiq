from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    # OpenAPI 3 schema + Swagger UI (F6). BOTH authenticated: the schema is a
    # complete map of every endpoint and payload shape, which is precisely what
    # someone probing the API would like handed to them. Generated from the real
    # views, so it cannot drift from the API the way a hand-written doc does.
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/schema/ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="schema-ui",
    ),
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
    # Module 6 — JD Library & AI JD Generator
    path("api/jd/", include("apps.jd.urls")),
    # Module 7 — Live Org Chart
    path("api/org/", include("apps.org.urls")),
    # Module 8 — Succession & Talent
    path("api/succession/", include("apps.succession.urls")),
    # Module 9 — Career Development (Roadmap LITE)
    path("api/career/", include("apps.career.urls")),
    # Module 11 — Administration (Admin Hub) + Audit Console
    path("api/admin/", include("apps.administration.urls")),
    path("api/audit/", include("apps.audit.urls")),
    # Module A — Analytics & Reporting
    path("api/analytics/", include("apps.analytics.urls")),
    # Module 12 — Integrations (Jira + Slack) config
    path("api/integrations/", include("apps.integrations.urls")),
    # Module 10 — AI Agents (Chat Assistant; other agents fill existing seams)
    path("api/ai/", include("apps.ai.urls")),
    # RW_BUILD_2 — Recognition (kudos card + feed)
    path("api/recognition/", include("apps.recognition.urls")),
    # RW_BUILD_3 — Weekly Check-ins
    path("api/checkins/", include("apps.checkins.urls")),
    # OAuth / OIDC login + callback (django-allauth)
    path("accounts/", include("allauth.urls")),
]
