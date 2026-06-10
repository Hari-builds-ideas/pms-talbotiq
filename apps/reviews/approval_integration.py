"""
Module-5 wiring: registers "review" as an approval-route artifact type.

This is the reference consumer that fills the single-step finalize seam Module 3
left. Registration happens in ReviewsConfig.ready(). The dependency is one-way
(reviews -> approvals); the engine never imports reviews — it calls back through
the registry callables defined here.

* resolve_context — the review's subject (employee), the subject's manager (for a
  ROLE=MANAGER step), and the protected set {subject}. SELF-APPROVAL DESIGN: only
  the SUBJECT (the employee being reviewed) is protected; the authoring manager is
  the legitimate first approver (a "Manager → HRBP" matrix is the canonical config,
  and protecting the manager would defeat it). The manager already human-approved
  the content in Module 3; the route is the additional org sign-off.
* on_route_complete — finalises the review via the EXISTING audited path
  (_finalize_apply): APPROVED -> FINALIZED, with the Module-3 CHECK constraint
  still governing.
* on_route_rejected — returns the review to its author (APPROVED -> EDITING) to
  revise; a re-submission later starts a FRESH route.

All callbacks run inside the engine's bound tenant context.
"""
from apps.approvals import registry
from apps.approvals.registry import ResolutionContext


def _resolve_context(artifact_id):
    from .models import Review

    review = Review.objects.get(id=artifact_id)
    subject = review.employee
    return ResolutionContext(
        subject=subject,
        manager=subject.manager,
        protected_user_ids={subject.id},
    )


def _on_route_complete(route):
    from . import state_machine as sm
    from .models import Review

    review = Review.objects.get(id=route.artifact_id)
    sm._finalize_apply(review, route.initiated_by)


def _on_route_rejected(route):
    from . import state_machine as sm
    from .models import Review

    review = Review.objects.get(id=route.artifact_id)
    sm.route_rejected(review, reason="Approval route rejected")


def register():
    """Idempotent — safe to call from AppConfig.ready()."""
    registry.register(
        "review",
        resolve_context=_resolve_context,
        on_route_complete=_on_route_complete,
        on_route_rejected=_on_route_rejected,
    )
