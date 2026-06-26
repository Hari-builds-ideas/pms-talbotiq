"""
Goal-tree routes, mounted under ``/api/goals/`` by the root urlconf.

Paths are declared WITHOUT a leading slash because they are appended to the
``api/goals/`` mount point. More specific literal paths (``templates/...``,
``kpis/...``) are declared before the bare ``<uuid:pk>`` goal detail so they
match first. RBAC gating lives on the views.
"""
from django.urls import path

from .views import (
    GoalAIDraftView,
    GoalApproveView,
    GoalDetailView,
    GoalKpiListCreateView,
    GoalListCreateView,
    KpiActualsView,
    KpiDetailView,
    KpiTemplateInstantiateView,
    KpiTemplateListView,
)

app_name = "goals"

urlpatterns = [
    path("", GoalListCreateView.as_view(), name="list-create"),
    # KPI templates (literal prefixes — before the goal <uuid:pk> route).
    path("templates/", KpiTemplateListView.as_view(), name="template-list"),
    path(
        "templates/instantiate",
        KpiTemplateInstantiateView.as_view(),
        name="template-instantiate",
    ),
    # AI goal-writer (RW_BUILD_5) — drafts a SMART goal; persists nothing.
    path("ai-draft", GoalAIDraftView.as_view(), name="ai-draft"),
    # KPI sub-resources.
    path("kpis/<uuid:pk>", KpiDetailView.as_view(), name="kpi-detail"),
    path("kpis/<uuid:kpi_id>/actuals", KpiActualsView.as_view(), name="kpi-actuals"),
    # Goal detail + actions + nested KPIs.
    path("<uuid:pk>", GoalDetailView.as_view(), name="detail"),
    path("<uuid:pk>/approve", GoalApproveView.as_view(), name="approve"),
    path("<uuid:goal_id>/kpis", GoalKpiListCreateView.as_view(), name="goal-kpis"),
]
