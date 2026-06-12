"""
Career exceptions. Scope violations (out-of-scope employee, cross-tenant) raise
DRF ``NotFound`` (404) directly in the services — a career roadmap the actor may
not see is indistinguishable from a non-existent one (no existence leak; the same
rule the other scoped modules follow). This file holds the input-validation
conflict.
"""
from rest_framework.exceptions import APIException


class InvalidCareerInput(APIException):
    """422: a career request is structurally invalid — e.g. neither or both of
    ``target_jd`` / ``target_position`` supplied, a non-PUBLISHED target JD, or an
    out-of-range progress tier."""

    status_code = 422
    default_code = "invalid_career_input"

    def __init__(self, detail, *, code="INVALID_CAREER_INPUT"):
        super().__init__({"detail": detail, "code": code})
