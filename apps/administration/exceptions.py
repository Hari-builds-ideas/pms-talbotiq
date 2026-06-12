"""
Administration exceptions. Input problems (a bad role, an email already in use)
are 422; the views resolve referenced users through the tenant-scoped manager so a
cross-tenant id is a 404 (handled there, not here).
"""
from rest_framework.exceptions import APIException


class InvalidAdminInput(APIException):
    """422: an admin request is structurally invalid — e.g. an unknown role or an
    email already in use within the tenant."""

    status_code = 422
    default_code = "invalid_admin_input"

    def __init__(self, detail, *, code="INVALID_ADMIN_INPUT"):
        super().__init__({"detail": detail, "code": code})
