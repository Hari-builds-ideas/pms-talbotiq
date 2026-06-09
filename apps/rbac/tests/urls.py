"""
Test-only urlconf, activated per-test via ``@pytest.mark.urls("apps.rbac.tests.urls")``.

Not referenced by the production ``config.urls`` — exists solely to mount the
RBAC end-to-end probe view.
"""
from django.urls import path

from .views import ScopedUserDetailView

urlpatterns = [
    path(
        "rbac-test/users/<uuid:user_id>/",
        ScopedUserDetailView.as_view(),
        name="rbac-test-user-detail",
    ),
]
