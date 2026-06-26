"""
Check-in routes, mounted under ``/api/checkins/`` by the root urlconf. Paths without
a leading slash (appended to the mount). The literal ``team`` route is declared
before the ``<uuid:pk>`` detail/action routes so it matches unambiguously.
"""
from django.urls import path

from .views import (
    CheckInDetailView,
    CheckInListCreateView,
    CheckInRespondView,
    TeamCheckInsView,
)

app_name = "checkins"

urlpatterns = [
    path("", CheckInListCreateView.as_view(), name="list-create"),
    path("team", TeamCheckInsView.as_view(), name="team"),
    path("<uuid:pk>", CheckInDetailView.as_view(), name="detail"),
    path("<uuid:pk>/respond", CheckInRespondView.as_view(), name="respond"),
]
