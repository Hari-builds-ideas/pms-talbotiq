"""
Recognition routes, mounted under ``/api/recognition/`` by the root urlconf.
Paths are declared WITHOUT a leading slash (appended to the mount point). The
literal ``meta`` / ``analytics`` routes are declared before the ``<uuid:pk>``
detail/action routes so they match unambiguously.
"""
from django.urls import path

from .views import (
    RecognitionAnalyticsView,
    RecognitionDetailView,
    RecognitionListCreateView,
    RecognitionMetaView,
    RecognitionReactView,
)

app_name = "recognition"

urlpatterns = [
    path("", RecognitionListCreateView.as_view(), name="list-create"),
    path("meta", RecognitionMetaView.as_view(), name="meta"),
    path("analytics", RecognitionAnalyticsView.as_view(), name="analytics"),
    path("<uuid:pk>", RecognitionDetailView.as_view(), name="detail"),
    path("<uuid:pk>/react", RecognitionReactView.as_view(), name="react"),
]
