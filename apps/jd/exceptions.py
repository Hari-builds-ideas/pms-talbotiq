"""JD lifecycle exceptions (status contract consistent with Modules 3/5)."""
from rest_framework.exceptions import APIException


class IllegalJDTransition(APIException):
    """409: a JD lifecycle transition attempted from the wrong status."""

    status_code = 409
    default_code = "illegal_jd_transition"

    def __init__(self, from_status, action):
        super().__init__(
            {
                "detail": f"Cannot {action} a job description in status {from_status}.",
                "code": "ILLEGAL_JD_TRANSITION",
                "from_status": from_status,
                "action": action,
            }
        )


class InvalidJDInput(APIException):
    """422: required JD fields are missing/empty (title, level, responsibilities,
    must-haves) — raised before generation and before submit-for-review."""

    status_code = 422
    default_code = "invalid_jd_input"

    def __init__(self, missing):
        super().__init__(
            {
                "detail": "Job description is missing required content: "
                + ", ".join(missing)
                + ".",
                "code": "INVALID_JD_INPUT",
                "missing": list(missing),
            }
        )
