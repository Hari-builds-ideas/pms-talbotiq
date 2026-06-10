"""
Approval-workflow routes, mounted under ``/api/approvals/`` by the root urlconf.

Paths are declared WITHOUT a leading slash (they are appended to the
``api/approvals/`` mount point). Literal prefixes (``workflows``, ``inbox``,
``routes``, ``steps``) precede their ``<uuid:pk>`` siblings so they match first.
RBAC gating lives on the views; routing/ordering/auth-of-assignment + legality
live in the engine; the serializers carry shape.
"""
from django.urls import path

from .views import (
    InboxView,
    RouteDetailView,
    RouteListView,
    StepApproveView,
    StepRejectView,
    WorkflowActivateView,
    WorkflowDeactivateView,
    WorkflowDetailView,
    WorkflowListCreateView,
)

app_name = "approvals"

urlpatterns = [
    # ── workflow templates (Admin / HRBP) ──
    path("workflows", WorkflowListCreateView.as_view(), name="workflow-list-create"),
    path("workflows/<uuid:pk>", WorkflowDetailView.as_view(), name="workflow-detail"),
    path(
        "workflows/<uuid:pk>/activate",
        WorkflowActivateView.as_view(),
        name="workflow-activate",
    ),
    path(
        "workflows/<uuid:pk>/deactivate",
        WorkflowDeactivateView.as_view(),
        name="workflow-deactivate",
    ),
    # ── the approver's inbox ──
    path("inbox", InboxView.as_view(), name="inbox"),
    # ── route trackers (literal list before <uuid:pk>) ──
    path("routes", RouteListView.as_view(), name="route-list"),
    path("routes/<uuid:pk>", RouteDetailView.as_view(), name="route-detail"),
    # ── deciding a step ──
    path("steps/<uuid:pk>/approve", StepApproveView.as_view(), name="step-approve"),
    path("steps/<uuid:pk>/reject", StepRejectView.as_view(), name="step-reject"),
]
