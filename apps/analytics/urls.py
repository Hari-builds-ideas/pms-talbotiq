"""
Analytics & Reporting routes, mounted under ``/api/analytics/`` by the root
urlconf.

Paths are declared WITHOUT a leading slash because they are appended to the
``api/analytics/`` mount point. Every endpoint is a thin ``RBACMixin`` ``APIView``
that gates its capability; scope + min-cohort suppression live in the services.
"""
from django.urls import path

from .views import (
    CalibrationGridView,
    DepartmentAnalyticsView,
    DepartmentExportView,
    IndividualAnalyticsView,
)

app_name = "analytics"

urlpatterns = [
    path("individual", IndividualAnalyticsView.as_view(), name="individual"),
    path("department", DepartmentAnalyticsView.as_view(), name="department"),
    path("calibration", CalibrationGridView.as_view(), name="calibration"),
    path("export", DepartmentExportView.as_view(), name="export"),
]
