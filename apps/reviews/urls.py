"""
Review routes, mounted under ``/api/reviews/`` by the root urlconf.

Paths are declared WITHOUT a leading slash because they are appended to the
``api/reviews/`` mount point. The literal ``calibration`` path is declared
before the bare ``<uuid:pk>`` detail so it matches first. RBAC gating lives on
the views; state legality / HITL rules live in the state machine.

``submit`` is the canonical save-the-draft-for-approval transition
(EDITING → PENDING_HUMAN_REVIEW); ``save-draft`` is an alias for the same view.
"""
from django.urls import path

from .views import (
    ReviewApproveView,
    ReviewAssessmentListCreateView,
    ReviewCalibrationView,
    ReviewDetailView,
    ReviewFinalizeView,
    ReviewListCreateView,
    ReviewRejectView,
    ReviewRequestAIDraftView,
    ReviewStartEditView,
    ReviewSubmitView,
    ReviewTimelineView,
)

app_name = "reviews"

urlpatterns = [
    path("", ReviewListCreateView.as_view(), name="list-create"),
    # Literal prefixes — before the bare <uuid:pk> detail route.
    path("calibration", ReviewCalibrationView.as_view(), name="calibration"),
    # Review detail + sub-resources.
    path("<uuid:pk>", ReviewDetailView.as_view(), name="detail"),
    path("<uuid:pk>/timeline", ReviewTimelineView.as_view(), name="timeline"),
    path(
        "<uuid:pk>/assessments",
        ReviewAssessmentListCreateView.as_view(),
        name="assessments",
    ),
    # State-machine transitions.
    path("<uuid:pk>/start-edit", ReviewStartEditView.as_view(), name="start-edit"),
    path("<uuid:pk>/submit", ReviewSubmitView.as_view(), name="submit"),
    path("<uuid:pk>/save-draft", ReviewSubmitView.as_view(), name="save-draft"),
    path("<uuid:pk>/approve", ReviewApproveView.as_view(), name="approve"),
    path("<uuid:pk>/reject", ReviewRejectView.as_view(), name="reject"),
    path("<uuid:pk>/finalize", ReviewFinalizeView.as_view(), name="finalize"),
    path(
        "<uuid:pk>/request-ai-draft",
        ReviewRequestAIDraftView.as_view(),
        name="request-ai-draft",
    ),
]
