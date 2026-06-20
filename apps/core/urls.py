from django.urls import path

from .views import MetricsView, ReadyzView, healthz

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("readyz", ReadyzView.as_view(), name="readyz"),
    path("metrics", MetricsView.as_view(), name="metrics"),
]
