"""
Review-flow API exceptions.

Status-code contract (per the Doc 2 §Module 4 diagram and the locked decisions):
  409 — an illegal state transition (the attempted from/to is named) or a
        structural conflict (e.g. creating a review against a non-ACTIVE cycle).
  422 — a semantically incomplete transition: finalizing without the HITL
        approval (HITL_APPROVAL_REQUIRED) or rejecting without a reason
        (REJECTION_REASON_REQUIRED).
"""
from rest_framework.exceptions import APIException


class IllegalTransition(APIException):
    """409: the transition is not in the legal table for the current state."""

    status_code = 409
    default_code = "illegal_transition"

    def __init__(self, from_state, action, to_state=None):
        detail = {
            "detail": (
                f"Illegal review transition: cannot {action} from state "
                f"{from_state}" + (f" to {to_state}" if to_state else "") + "."
            ),
            "code": "ILLEGAL_TRANSITION",
            "from_state": from_state,
            "action": action,
        }
        if to_state:
            detail["to_state"] = to_state
        super().__init__(detail)


class HITLApprovalRequired(APIException):
    """422: cannot finalize while human_reviewer_id is NULL (the HITL gate)."""

    status_code = 422
    default_code = "hitl_approval_required"

    def __init__(self, from_state):
        super().__init__(
            {
                "detail": (
                    "Cannot finalize: a human must approve first "
                    f"(state is {from_state}, human_reviewer is not set)."
                ),
                "code": "HITL_APPROVAL_REQUIRED",
                "from_state": from_state,
            }
        )


class RejectionReasonRequired(APIException):
    """422: the reject transition requires a non-empty reason."""

    status_code = 422
    default_code = "rejection_reason_required"

    def __init__(self):
        super().__init__(
            {
                "detail": "A non-empty rejected_reason is required to reject a review.",
                "code": "REJECTION_REASON_REQUIRED",
            }
        )


class CycleNotActive(APIException):
    """409: reviews may only be created while their cycle is ACTIVE."""

    status_code = 409
    default_code = "cycle_not_active"

    def __init__(self, cycle_status):
        super().__init__(
            {
                "detail": (
                    "A review can only be created in an ACTIVE cycle "
                    f"(cycle is {cycle_status})."
                ),
                "code": "CYCLE_NOT_ACTIVE",
                "cycle_status": cycle_status,
            }
        )
