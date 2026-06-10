"""
Feedback-flow API exceptions.

Status contract (consistent with Module 3): 409 for structural/state conflicts
(submitting outside COLLECTING, editing after close, double submission); 403 for
missing authorisation (no invitation). DRF's handler maps these automatically.
"""
from rest_framework.exceptions import APIException


class CycleNotCollecting(APIException):
    """409: 360 feedback is only accepted while the cycle is COLLECTING."""

    status_code = 409
    default_code = "cycle_not_collecting"

    def __init__(self, cycle_status):
        super().__init__(
            {
                "detail": (
                    "360 feedback can only be submitted while the cycle is "
                    f"COLLECTING (cycle is {cycle_status})."
                ),
                "code": "CYCLE_NOT_COLLECTING",
                "cycle_status": cycle_status,
            }
        )


class IllegalCycleTransition(APIException):
    """409: open/close called from the wrong cycle status."""

    status_code = 409
    default_code = "illegal_cycle_transition"

    def __init__(self, from_status, action):
        super().__init__(
            {
                "detail": f"Cannot {action} a feedback cycle in status {from_status}.",
                "code": "ILLEGAL_CYCLE_TRANSITION",
                "from_status": from_status,
                "action": action,
            }
        )


class InvitationRequired(APIException):
    """403: 360 feedback requires a matching PENDING FeedbackRequest."""

    status_code = 403
    default_code = "invitation_required"

    def __init__(self):
        super().__init__(
            {
                "detail": (
                    "360 feedback requires a pending invitation (FeedbackRequest) "
                    "for this cycle."
                ),
                "code": "INVITATION_REQUIRED",
            }
        )


class FeedbackImmutable(APIException):
    """409: feedback cannot be changed once its cycle is CLOSED."""

    status_code = 409
    default_code = "feedback_immutable"

    def __init__(self):
        super().__init__(
            {
                "detail": "Feedback is immutable once its cycle is CLOSED.",
                "code": "FEEDBACK_IMMUTABLE",
            }
        )
