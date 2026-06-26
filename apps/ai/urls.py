"""AI routes, mounted under ``/api/ai/``: the read-only Chat Assistant + the
async AI job poll surface (BUILD_2)."""
from django.urls import path

from .views import (
    AIJobDetailView,
    AIJobListView,
    ChatActionExecuteView,
    ChatView,
    MeetingSummaryView,
    NudgesView,
    ReviewQualityView,
    StaleGoalsView,
)

app_name = "ai"

urlpatterns = [
    path("chat", ChatView.as_view(), name="chat"),
    path("actions/execute", ChatActionExecuteView.as_view(), name="action-execute"),
    path("meeting-summary", MeetingSummaryView.as_view(), name="meeting-summary"),
    path("review-quality", ReviewQualityView.as_view(), name="review-quality"),
    path("stale-goals", StaleGoalsView.as_view(), name="stale-goals"),
    path("nudges", NudgesView.as_view(), name="nudges"),
    path("jobs", AIJobListView.as_view(), name="job-list"),
    path("jobs/<uuid:pk>", AIJobDetailView.as_view(), name="job-detail"),
]
