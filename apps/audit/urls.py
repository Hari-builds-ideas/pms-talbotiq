"""
Audit Console routes, mounted under ``/api/audit/`` by the root urlconf.

A single READ-ONLY route: the console is a ``ListAPIView``, so only ``GET`` is
exposed (a write is a 405). The audit log is append-only — there is no write
surface here.
"""
from django.urls import path

from .views import AuditLogConsoleView

app_name = "audit"

urlpatterns = [
    path("logs", AuditLogConsoleView.as_view(), name="logs"),
]
