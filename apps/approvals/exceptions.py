"""
Approval-engine exceptions.

Status contract: 409 for state/ordering conflicts (deciding a non-active or
already-decided step, a second route for an artifact, completing a done route);
422 for an unresolvable route at start; 403 (PermissionDenied) for an actor who
is not the assigned approver / role-holder, or who would self-approve.
"""
from rest_framework.exceptions import APIException, PermissionDenied  # noqa: F401


class IllegalDecision(APIException):
    """409: the step is not currently decidable (wrong order / already decided /
    route not in progress)."""

    status_code = 409
    default_code = "illegal_decision"

    def __init__(self, detail, *, step_status=None, route_status=None):
        body = {"detail": detail, "code": "ILLEGAL_DECISION"}
        if step_status is not None:
            body["step_status"] = step_status
        if route_status is not None:
            body["route_status"] = route_status
        super().__init__(body)


class ActiveRouteExists(APIException):
    """409: an in-progress route already exists for this artifact."""

    status_code = 409
    default_code = "active_route_exists"

    def __init__(self, artifact_type, artifact_id):
        super().__init__(
            {
                "detail": (
                    f"An in-progress approval route already exists for "
                    f"{artifact_type}:{artifact_id}."
                ),
                "code": "ACTIVE_ROUTE_EXISTS",
            }
        )


class RouteApproverUnresolvable(APIException):
    """422: a required step's approver cannot be resolved (e.g. ROLE=MANAGER but
    the subject has no manager and no escalation target). No half-built route."""

    status_code = 422
    default_code = "route_approver_unresolvable"

    def __init__(self, reason):
        super().__init__(
            {
                "detail": f"Cannot start the approval route: {reason}.",
                "code": "ROUTE_APPROVER_UNRESOLVABLE",
            }
        )


class UnknownArtifactType(APIException):
    """500-ish config error surfaced as 400: artifact type not registered."""

    status_code = 400
    default_code = "unknown_artifact_type"

    def __init__(self, artifact_type):
        super().__init__(
            {
                "detail": f"No approval handler registered for artifact type '{artifact_type}'.",
                "code": "UNKNOWN_ARTIFACT_TYPE",
            }
        )
