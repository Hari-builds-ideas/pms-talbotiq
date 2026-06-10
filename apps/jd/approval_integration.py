"""
Module-5 wiring: registers "jd" as an approval-route artifact type — the SECOND
consumer of the approval engine, proving it is generic (reviews was the first).

A JD has NO employee subject, so ``resolve_context`` returns subject/manager =
None: a workflow misconfigured with a ROLE=MANAGER step is therefore correctly
rejected by the engine's existing 422 ROUTE_APPROVER_UNRESOLVABLE. JD workflows
use ROLE=HRBP/ADMIN or NAMED approvers. ``protected_user_ids = {created_by}`` —
the author can never approve their own JD's route.

* on_route_complete -> the audited PUBLISH transition.
* on_route_rejected -> return the JD to PENDING_HUMAN_REVIEW for the author.

Dependency is one-way (jd -> approvals); the engine never imports jd. Callbacks
run inside the engine's bound tenant context.
"""
from apps.approvals import registry
from apps.approvals.registry import ResolutionContext


def _resolve_context(artifact_id):
    from .models import JobDescription

    jd = JobDescription.objects.get(id=artifact_id)
    protected = {jd.created_by_id} if jd.created_by_id else set()
    # No employee subject + no manager: a MANAGER step is unresolvable by design.
    return ResolutionContext(subject=None, manager=None, protected_user_ids=protected)


def _on_route_complete(route):
    from . import lifecycle
    from .models import JobDescription

    jd = JobDescription.objects.get(id=route.artifact_id)
    lifecycle._publish(jd, route.initiated_by)


def _on_route_rejected(route):
    from . import lifecycle
    from .models import JobDescription

    jd = JobDescription.objects.get(id=route.artifact_id)
    lifecycle.route_rejected(jd, reason="Approval route rejected")


def register():
    """Idempotent — safe to call from AppConfig.ready()."""
    registry.register(
        "jd",
        resolve_context=_resolve_context,
        on_route_complete=_on_route_complete,
        on_route_rejected=_on_route_rejected,
    )
