"""
Feedback routes, mounted under ``/api/feedback/`` by the root urlconf.

Paths are declared WITHOUT a leading slash because they are appended to the
``api/feedback/`` mount point. Literal prefixes (``requests/mine``,
``summaries/review``) are declared before their sibling ``<uuid:pk>`` routes so
they match first. RBAC gating lives on the views; lifecycle legality and the
giver-anonymity rules live in the services / anonymize layer / serializers.
"""
from django.urls import path

from .views import (
    ContinuousFeedbackView,
    CycleAnonymizedView,
    CycleCloseView,
    CycleOpenView,
    CycleRequestListCreateView,
    CycleSummarizeView,
    CycleSummaryView,
    FeedbackCycleListCreateView,
    FeedbackItemEditView,
    GiveFeedbackView,
    MyCyclesView,
    MyFeedbackView,
    MyRequestsView,
    OneOnOneDetailView,
    OneOnOneListCreateView,
    ReceivedFeedbackView,
    RequestDeclineView,
    SummaryApproveView,
    SummaryReviewQueueView,
)

app_name = "feedback"

urlpatterns = [
    # ── 360 cycles (manager surface) ──
    # Literal "my-cycles" (subject self-discovery) declared before the
    # "cycles/<uuid:pk>" family; it never collides with "cycles" itself.
    path("my-cycles", MyCyclesView.as_view(), name="my-cycles"),
    path("cycles", FeedbackCycleListCreateView.as_view(), name="cycle-list-create"),
    path("cycles/<uuid:pk>/open", CycleOpenView.as_view(), name="cycle-open"),
    path("cycles/<uuid:pk>/close", CycleCloseView.as_view(), name="cycle-close"),
    path("cycles/<uuid:pk>/summarize", CycleSummarizeView.as_view(), name="cycle-summarize"),
    path(
        "cycles/<uuid:pk>/requests",
        CycleRequestListCreateView.as_view(),
        name="cycle-requests",
    ),
    # ── giving feedback (giver surface) ──
    path("cycles/<uuid:pk>/give", GiveFeedbackView.as_view(), name="cycle-give"),
    path("continuous", ContinuousFeedbackView.as_view(), name="continuous"),
    path("mine", MyFeedbackView.as_view(), name="mine"),
    path("items/<uuid:pk>", FeedbackItemEditView.as_view(), name="item-edit"),
    # ── invitations (giver surface; literal before <uuid:pk>) ──
    path("requests/mine", MyRequestsView.as_view(), name="requests-mine"),
    path("requests/<uuid:pk>/decline", RequestDeclineView.as_view(), name="request-decline"),
    # ── receiving feedback (recipient surface) ──
    path("received", ReceivedFeedbackView.as_view(), name="received"),
    path("cycles/<uuid:pk>/anonymized", CycleAnonymizedView.as_view(), name="cycle-anonymized"),
    path("cycles/<uuid:pk>/summary", CycleSummaryView.as_view(), name="cycle-summary"),
    # ── summaries (HRBP surface; literal before <uuid:pk>) ──
    path("summaries/review", SummaryReviewQueueView.as_view(), name="summary-review-queue"),
    path("summaries/<uuid:pk>/approve", SummaryApproveView.as_view(), name="summary-approve"),
    # ── 1:1 notes (participants only) ──
    path("one-on-ones", OneOnOneListCreateView.as_view(), name="one-on-one-list-create"),
    path("one-on-ones/<uuid:pk>", OneOnOneDetailView.as_view(), name="one-on-one-detail"),
]
