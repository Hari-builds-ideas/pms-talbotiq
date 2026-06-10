"""
Succession & Talent routes, mounted under ``/api/succession/`` by the root
urlconf.

Paths are declared WITHOUT a leading slash because they are appended to the
``api/succession/`` mount point. The literal prefixes (``dashboard``,
``critical-roles``, ``bench``, ``nine-box``, ``plans``) are declared so the
literal action routes match before the bare ``<uuid:pk>`` detail / action routes.

SENSITIVITY lives on the views: every one subclasses ``SuccessionMixin`` so the
module is invisible (404) to non-management roles; RBAC capability gating is on
the views; scope (out-of-tier → 404) lives in the services / plans.
"""
from django.urls import path

from .views import (
    BenchListCreateView,
    BenchReadinessView,
    CriticalRoleArchiveView,
    CriticalRoleDetailView,
    CriticalRoleListCreateView,
    DashboardView,
    GenerateAnalysisView,
    KnowledgeRiskView,
    NineBoxListCreateView,
    PlanActionItemView,
    PlanDetailView,
    PlanEnrichView,
    PlanPublishView,
)

app_name = "succession"

urlpatterns = [
    # Dashboard.
    path("dashboard", DashboardView.as_view(), name="dashboard"),
    # Critical roles — list/create before the bare <uuid:pk> detail / action routes.
    path(
        "critical-roles",
        CriticalRoleListCreateView.as_view(),
        name="critical-role-list-create",
    ),
    path(
        "critical-roles/<uuid:pk>",
        CriticalRoleDetailView.as_view(),
        name="critical-role-detail",
    ),
    path(
        "critical-roles/<uuid:pk>/knowledge-risk",
        KnowledgeRiskView.as_view(),
        name="critical-role-knowledge-risk",
    ),
    path(
        "critical-roles/<uuid:pk>/archive",
        CriticalRoleArchiveView.as_view(),
        name="critical-role-archive",
    ),
    path(
        "critical-roles/<uuid:pk>/bench",
        BenchListCreateView.as_view(),
        name="critical-role-bench",
    ),
    path(
        "critical-roles/<uuid:pk>/generate",
        GenerateAnalysisView.as_view(),
        name="critical-role-generate",
    ),
    # Bench.
    path(
        "bench/<uuid:pk>/readiness",
        BenchReadinessView.as_view(),
        name="bench-readiness",
    ),
    # 9-box.
    path("nine-box", NineBoxListCreateView.as_view(), name="nine-box"),
    # Plans.
    path("plans/<uuid:pk>", PlanDetailView.as_view(), name="plan-detail"),
    path(
        "plans/<uuid:pk>/action-item",
        PlanActionItemView.as_view(),
        name="plan-action-item",
    ),
    path("plans/<uuid:pk>/publish", PlanPublishView.as_view(), name="plan-publish"),
    path("plans/<uuid:pk>/enrich", PlanEnrichView.as_view(), name="plan-enrich"),
]
