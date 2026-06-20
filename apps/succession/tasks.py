"""
Celery entry point for the Agent-4 (Successor Planning) enrichment seam.

``enrich_succession_with_agent4`` is the single way Agent 4 enriches a plan. It is
a ``@shared_task`` so production can ``.delay()``, but it is also directly callable
synchronously (tests + the API view call it inline).

It binds the tenant off-request (the recurring lesson — scoped managers fail
closed otherwise), then resolves the provider. With NONE configured it logs a
clear warning and returns ``{"enriched": False, "reason": "no_provider"}`` — and,
critically, the DETERMINISTIC plan is left COMPLETELY INTACT and still valid (the
baseline is core, not faked; this is the key difference from the other AI seams).
The API view surfaces this as a loud 503 ("Agent 4 lands in Module 10").

A configured provider (Module 10) reads internal CycleScores/goals + ANONYMISED
360, produces an enriched analysis, and locks a NEW plan (source=AI) with a
confidence score PENDING_HUMAN_REVIEW for the HRBP to re-review — never publishing
directly.
"""
import logging

from celery import shared_task

from apps.tenancy.context import tenant_context

from .agent4 import SuccessionAnalyzerNotConfiguredError, get_provider
from .models import SuccessionPlan

logger = logging.getLogger("pms.succession.agent4")


@shared_task
def enrich_succession_with_agent4(tenant_id, plan_id, actor_id=None):
    """Enrich the deterministic plan ``plan_id`` (within ``tenant_id``) with
    Agent 4, HITL-gated. Returns a summary dict; ``{"enriched": False, ...}`` on
    any skip — the deterministic plan is never mutated on the no-provider path."""
    with tenant_context(tenant_id):
        plan = SuccessionPlan.objects.filter(id=plan_id).first()
        if plan is None:
            logger.warning(
                "Agent-4 enrich skipped for tenant=%s: plan=%s not found.",
                tenant_id,
                plan_id,
            )
            return {"enriched": False, "reason": "not_found"}

        provider = get_provider()
        if not getattr(provider, "configured", False):
            logger.warning(
                "Agent-4 enrich skipped for tenant=%s plan=%s: no Succession "
                "Analyzer provider configured (Agent 4 lands in Module 10); the "
                "deterministic plan is left intact.",
                tenant_id,
                plan_id,
            )
            return {"enriched": False, "reason": "no_provider"}

        if actor_id is None:
            logger.warning(
                "Agent-4 enrich refused for tenant=%s plan=%s: no actor_id; an "
                "accountable human requester is required.",
                tenant_id,
                plan_id,
            )
            return {"enriched": False, "reason": "actor_required"}

        from apps.identity.models import User

        actor = User.objects.filter(id=actor_id).first()
        if actor is None:
            logger.warning(
                "Agent-4 enrich refused for tenant=%s plan=%s: actor=%s not found.",
                tenant_id,
                plan_id,
                actor_id,
            )
            return {"enriched": False, "reason": "actor_not_found"}

        critical_role = plan.critical_role
        try:
            result = provider.analyze(critical_role=critical_role, plan=plan)
        except SuccessionAnalyzerNotConfiguredError:
            logger.warning(
                "Agent-4 enrich skipped for tenant=%s plan=%s: provider reported "
                "not configured; deterministic plan intact.",
                tenant_id,
                plan_id,
            )
            return {"enriched": False, "reason": "no_provider"}
        except Exception as exc:  # noqa: BLE001 - a provider bug must not crash the worker
            reason = (
                "budget_exceeded"
                if getattr(exc, "gateway_status", None) == "BUDGET_EXCEEDED"
                else "provider_error"
            )
            logger.error(
                "Agent-4 provider failed for tenant=%s plan=%s; deterministic plan "
                "left intact for ops to inspect.",
                tenant_id,
                plan_id,
                exc_info=True,
            )
            return {"enriched": False, "reason": reason}

        # A NEW AI plan, locked PENDING_HUMAN_REVIEW for HRBP re-review — the
        # deterministic baseline is never overwritten.
        from django.utils import timezone

        ai_plan = SuccessionPlan.objects.create(
            tenant_id=tenant_id,
            critical_role=critical_role,
            status=SuccessionPlan.Status.PENDING_HUMAN_REVIEW,
            ranked_bench=result["ranked_bench"],
            coverage_status=result["coverage_status"],
            red_flags=result.get("red_flags", []),
            action_items=[],
            source=SuccessionPlan.Source.AI,
            confidence_score=result.get("confidence_score"),
            generated_at=timezone.now(),
        )
        return {"enriched": True, "plan_id": str(ai_plan.id), "status": ai_plan.status}
