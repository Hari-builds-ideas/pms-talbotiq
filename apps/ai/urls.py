"""AI routes, mounted under ``/api/ai/``: the read-only Chat Assistant + the
async AI job poll surface (BUILD_2)."""
from django.urls import path

from .views import (
    AIJobDetailView,
    AIJobListView,
    ChatActionExecuteView,
    ChatView,
    NudgesView,
)

app_name = "ai"

urlpatterns = [
    path("chat", ChatView.as_view(), name="chat"),
    path("actions/execute", ChatActionExecuteView.as_view(), name="action-execute"),
    path("nudges", NudgesView.as_view(), name="nudges"),
    path("jobs", AIJobListView.as_view(), name="job-list"),
    path("jobs/<uuid:pk>", AIJobDetailView.as_view(), name="job-detail"),
]
