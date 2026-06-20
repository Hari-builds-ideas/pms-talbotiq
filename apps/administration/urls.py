"""
Admin Hub routes, mounted under ``/api/admin/`` by the root urlconf.

Paths are declared WITHOUT a leading slash because they are appended to the
``api/admin/`` mount point. Every endpoint is Admin-only (see ``views.py``).
"""
from django.urls import path

from .views import (
    TenantConfigView,
    UserDeactivateView,
    UserDisplayNameView,
    UserListCreateView,
    UserReactivateView,
    UserReportingLineView,
    UserRoleView,
    UserStatsView,
)

app_name = "administration"

urlpatterns = [
    path("users", UserListCreateView.as_view(), name="users"),
    path("users/stats", UserStatsView.as_view(), name="user-stats"),
    path("users/<uuid:pk>/role", UserRoleView.as_view(), name="user-role"),
    path("users/<uuid:pk>/display-name", UserDisplayNameView.as_view(), name="user-display-name"),
    path("users/<uuid:pk>/deactivate", UserDeactivateView.as_view(), name="user-deactivate"),
    path("users/<uuid:pk>/reactivate", UserReactivateView.as_view(), name="user-reactivate"),
    path(
        "users/<uuid:pk>/reporting-line",
        UserReportingLineView.as_view(),
        name="user-reporting-line",
    ),
    path("tenant-config", TenantConfigView.as_view(), name="tenant-config"),
]
