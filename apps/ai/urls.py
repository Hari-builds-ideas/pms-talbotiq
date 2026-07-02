"""AI routes, mounted under ``/api/ai/``: the read-only Chat Assistant + the
async AI job poll surface (BUILD_2)."""
from django.urls import path

from .views import (
    AIJobDetailView,
    AIJobListView,
    ChatActionExecuteView,
    ChatPlanCreateView,
    ChatPlanStepApproveView,
    ChatSessionDetailView,
    ChatSessionListView,
    ChatView,
    MeetingSummaryView,
    NLSearchView,
    NudgesView,
    ReviewQualityView,
    StaleGoalsView,
)

app_name = "ai"

urlpatterns = [
    path("chat", ChatView.as_view(), name="chat"),
    path("actions/execute", ChatActionExecuteView.as_view(), name="action-execute"),
    # Agentic chat V2 (OVERNIGHT_A): plan → per-step approve + session memory.
    path("chat/plan", ChatPlanCreateView.as_view(), name="chat-plan"),
    path("chat/plan/<uuid:plan_id>/step/<uuid:step_id>/approve",
         ChatPlanStepApproveView.as_view(), name="chat-plan-step-approve"),
    path("chat/sessions", ChatSessionListView.as_view(), name="chat-sessions"),
    path("chat/sessions/<uuid:session_id>", ChatSessionDetailView.as_view(), name="chat-session-detail"),
    path("meeting-summary", MeetingSummaryView.as_view(), name="meeting-summary"),
    path("review-quality", ReviewQualityView.as_view(), name="review-quality"),
    path("stale-goals", StaleGoalsView.as_view(), name="stale-goals"),
    path("search", NLSearchView.as_view(), name="nl-search"),
    path("nudges", NudgesView.as_view(), name="nudges"),
    path("jobs", AIJobListView.as_view(), name="job-list"),
    path("jobs/<uuid:pk>", AIJobDetailView.as_view(), name="job-detail"),
]
