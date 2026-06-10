"""
Celery entry point for the Agent-1 (Review Assistant) seam.

``draft_review_with_agent1`` is the single way an AI draft is produced: it
drives the audited state machine (DRAFT -> AI_DRAFTING -> PENDING_HUMAN_REVIEW)
around whatever provider ``apps.reviews.agent1.get_provider`` resolves. It is a
``@shared_task`` so production calls ``.delay()``, but it is also directly
callable synchronously (tests and the API view call it inline).

With no provider configured it logs a clear warning and skips cleanly — the
review STAYS in DRAFT, untouched, so the manual path is never blocked and no
fake draft is ever written. The ``configured`` check happens BEFORE the
``request_ai_draft`` transition precisely so an unconfigured provider can never
strand a review in AI_DRAFTING.
"""
import logging

from celery import shared_task

from apps.tenancy.context import tenant_context

from . import state_machine
from .agent1 import ReviewAssistantNotConfiguredError, get_provider
from .models import Review

logger = logging.getLogger("pms.reviews.agent1")


@shared_task
def draft_review_with_agent1(tenant_id, review_id, actor_id=None):
    """Draft ``review_id`` (within ``tenant_id``) with Agent 1, HITL-gated.

    ``actor_id`` is the requesting human (the manager hitting the API). The
    seam demands an accountable requester: ``request_ai_draft`` is RBAC-checked
    against that actor, so a configured provider with no actor is refused.

    Returns a summary dict; ``{"drafted": False, "reason": ...}`` on any skip.
    Error handling is deliberately asymmetric around the transition:

    - BEFORE ``request_ai_draft``: every check (provider configured, review
      exists, state is DRAFT, actor present) skips cleanly, review untouched.
    - AFTER it, a provider failure leaves the review in AI_DRAFTING on purpose:
      the audit trail + timeline already record the attempt, and the stuck
      state is the visible signal for ops to inspect — silently rolling back
      to DRAFT would hide the failure.
    """
    with tenant_context(tenant_id):
        review = Review.objects.filter(id=review_id).first()
        if review is None:
            logger.warning(
                "Agent-1 draft skipped for tenant=%s: review=%s not found.",
                tenant_id,
                review_id,
            )
            return {"drafted": False, "reason": "not_found"}

        provider = get_provider()
        if not getattr(provider, "configured", False):
            logger.warning(
                "Agent-1 draft skipped for tenant=%s review=%s: no Review "
                "Assistant provider configured (Agent 1 lands in Module 10); "
                "review left in %s.",
                tenant_id,
                review_id,
                review.state,
            )
            return {"drafted": False, "reason": "no_provider"}

        if review.state != Review.State.DRAFT:
            return {"drafted": False, "reason": f"bad_state:{review.state}"}

        if actor_id is None:
            logger.warning(
                "Agent-1 draft refused for tenant=%s review=%s: no actor_id; "
                "an accountable human requester is required.",
                tenant_id,
                review_id,
            )
            return {"drafted": False, "reason": "actor_required"}

        from apps.identity.models import User

        actor = User.objects.filter(id=actor_id).first()
        if actor is None:
            logger.warning(
                "Agent-1 draft refused for tenant=%s review=%s: actor=%s not "
                "found in tenant.",
                tenant_id,
                review_id,
                actor_id,
            )
            return {"drafted": False, "reason": "actor_not_found"}

        # RBAC-checked, audited DRAFT -> AI_DRAFTING.
        state_machine.request_ai_draft(review, actor)

        try:
            result = provider.draft(review)
        except ReviewAssistantNotConfiguredError:
            # A configured-looking provider that still can't serve. Logged as
            # no_provider; the review stays in AI_DRAFTING (see docstring).
            logger.warning(
                "Agent-1 draft skipped for tenant=%s review=%s: provider "
                "reported not configured; review left in AI_DRAFTING.",
                tenant_id,
                review_id,
            )
            return {"drafted": False, "reason": "no_provider"}
        except Exception:  # noqa: BLE001 - a provider bug must not crash the worker
            logger.error(
                "Agent-1 provider failed for tenant=%s review=%s; review left "
                "in AI_DRAFTING for ops to inspect.",
                tenant_id,
                review_id,
                exc_info=True,
            )
            return {"drafted": False, "reason": "provider_error"}

        # SYSTEM transition: lock the draft PENDING_HUMAN_REVIEW (HITL gate).
        state_machine.ai_draft_ready(
            review,
            draft_body=result["draft_body"],
            confidence_score=result.get("confidence_score"),
            citations=result.get("citations"),
        )
        return {"drafted": True, "review_id": str(review.id), "state": review.state}
