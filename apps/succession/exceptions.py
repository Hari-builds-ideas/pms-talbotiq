"""
Succession exceptions. Scope violations (out-of-tier manager, cross-tenant, or
any employee access) raise DRF ``NotFound`` (404) directly — the module must not
leak its existence. This file holds the one state-machine conflict.
"""
from rest_framework.exceptions import APIException


class IllegalPlanTransition(APIException):
    """409: a succession-plan action is illegal from the plan's current status
    (e.g. publishing a plan that has not been through PENDING_HUMAN_REVIEW)."""

    status_code = 409
    default_code = "illegal_plan_transition"

    def __init__(self, from_status, action):
        super().__init__(
            {
                "detail": f"Cannot {action} a succession plan in status {from_status}.",
                "code": "ILLEGAL_PLAN_TRANSITION",
                "from_status": from_status,
                "action": action,
            }
        )
