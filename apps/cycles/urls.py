"""
Cycle routes, mounted under ``/api/cycles/`` by the root urlconf.

Paths are declared WITHOUT a leading slash because they are appended to the
``api/cycles/`` mount point. RBAC gating lives on the views.
"""
from django.urls import path

from .views import (
    CycleDetailView,
    CycleListCreateView,
    CycleRecomputeView,
    CycleScoresView,
    EmployeeCycleScoreView,
    MyCycleScoreView,
)

app_name = "cycles"

urlpatterns = [
    path("", CycleListCreateView.as_view(), name="list-create"),
    path("<uuid:pk>", CycleDetailView.as_view(), name="detail"),
    path("<uuid:cycle_id>/recompute", CycleRecomputeView.as_view(), name="recompute"),
    # ``scores/me`` (literal) is declared before ``scores/<uuid:employee_id>`` so
    # the literal wins; "me" is not a valid uuid so it never matches the converter.
    path("<uuid:cycle_id>/scores/me", MyCycleScoreView.as_view(), name="my-score"),
    path(
        "<uuid:cycle_id>/scores/<uuid:employee_id>",
        EmployeeCycleScoreView.as_view(),
        name="employee-score",
    ),
    path("<uuid:cycle_id>/scores", CycleScoresView.as_view(), name="scores"),
]
