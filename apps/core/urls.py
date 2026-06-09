from django.urls import path

from .views import ReadyzView, healthz

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("readyz", ReadyzView.as_view(), name="readyz"),
]
