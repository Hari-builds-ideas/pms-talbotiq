"""
Org-chart exceptions.

Status contract (matches the Module-6 JD style): 409 for an illegal position
state change (filling a non-OPEN position, closing a CLOSED one); 422 for a
reporting cycle or invalid input (an inactive / cross-tenant manager, a
non-published / cross-tenant JD link).
"""
from rest_framework.exceptions import APIException


class PositionAlreadyFilled(APIException):
    """409: a fill was attempted on a position that is already FILLED."""

    status_code = 409
    default_code = "position_already_filled"

    def __init__(self, position_id):
        super().__init__(
            {
                "detail": "This position is already filled.",
                "code": "POSITION_ALREADY_FILLED",
                "position": str(position_id),
            }
        )


class IllegalPositionTransition(APIException):
    """409: the position is not in a state from which this action is legal
    (e.g. filling or closing a CLOSED position)."""

    status_code = 409
    default_code = "illegal_position_transition"

    def __init__(self, from_status, action):
        super().__init__(
            {
                "detail": f"Cannot {action} a position in status {from_status}.",
                "code": "ILLEGAL_POSITION_TRANSITION",
                "from_status": from_status,
                "action": action,
            }
        )


class ReportingCycle(APIException):
    """422: a reassignment would create a cycle in the reporting tree (the new
    manager is the user themselves or sits within the user's own subtree)."""

    status_code = 422
    default_code = "reporting_cycle"

    def __init__(self, user_id, new_manager_id):
        super().__init__(
            {
                "detail": (
                    "This reassignment would create a cycle in the reporting "
                    "line: the proposed manager reports (directly or indirectly) "
                    "to the user being moved."
                ),
                "code": "REPORTING_CYCLE",
                "user": str(user_id),
                "new_manager": str(new_manager_id),
            }
        )


class InvalidOrgInput(APIException):
    """422: an org input is invalid — an inactive / cross-tenant manager, or a
    JD that is not PUBLISHED / not in the tenant."""

    status_code = 422
    default_code = "invalid_org_input"

    def __init__(self, reason, detail):
        super().__init__({"detail": detail, "code": "INVALID_ORG_INPUT", "reason": reason})
