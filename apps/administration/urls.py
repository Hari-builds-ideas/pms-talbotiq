"""
Admin Hub routes, mounted under ``/api/admin/`` by the root urlconf.

Paths are declared WITHOUT a leading slash because they are appended to the
``api/admin/`` mount point. Every endpoint is Admin-only (see ``views.py``).
"""
from django.urls import path

from apps.identity.invite_views import (
    InvitationAdminView,
    InvitationResendView,
    InvitationRevokeView,
)

from .views import (
    EmployeeImportView,
    OrgSettingsView,
    TenantConfigView,
    UserDeactivateView,
    UserDisplayNameView,
    UserExportView,
    UserListCreateView,
    UserOrgProfileView,
    UserReactivateView,
    UserReportingLineView,
    UserRoleView,
    UserStatsView,
)

app_name = "administration"

urlpatterns = [
    path("users", UserListCreateView.as_view(), name="users"),
    # ─── bulk employee onboarding (CSV import; INVITE_USERS — HRBP+) ───
    path("users/import", EmployeeImportView.as_view(), name="users-import"),
    path("users/stats", UserStatsView.as_view(), name="user-stats"),
    path("users/<uuid:pk>/role", UserRoleView.as_view(), name="user-role"),
    path("users/<uuid:pk>/display-name", UserDisplayNameView.as_view(), name="user-display-name"),
    path("users/<uuid:pk>/profile", UserOrgProfileView.as_view(), name="user-org-profile"),
    # ─── data subject rights (D1/D2; MANAGE_TENANT — Admin) ───
    path("users/<uuid:pk>/export", UserExportView.as_view(), name="user-export"),
    # ─── invitations (PHASE2 L1.2; INVITE_USERS — HRBP+) ───
    path("invitations", InvitationAdminView.as_view(), name="invitations"),
    path("invitations/<uuid:pk>/revoke", InvitationRevokeView.as_view(), name="invitation-revoke"),
    path("invitations/<uuid:pk>/resend", InvitationResendView.as_view(), name="invitation-resend"),
    path("users/<uuid:pk>/deactivate", UserDeactivateView.as_view(), name="user-deactivate"),
    path("users/<uuid:pk>/reactivate", UserReactivateView.as_view(), name="user-reactivate"),
    path(
        "users/<uuid:pk>/reporting-line",
        UserReportingLineView.as_view(),
        name="user-reporting-line",
    ),
    path("tenant-config", TenantConfigView.as_view(), name="tenant-config"),
    # ─── org settings + branding hooks (PHASE2 L1.5; MANAGE_TENANT — Admin) ───
    path("org-settings", OrgSettingsView.as_view(), name="org-settings"),
]
