"""
Celery entry point for the Career Roadmap agent (Module 10) enrichment seam.

``generate_roadmap`` is the AI-enrich path. It binds the tenant off-request (the
recurring lesson — scoped managers fail closed otherwise), computes the
deterministic gap ALWAYS, then resolves the provider. With NONE configured it
logs-and-skips → ``{"generated": False, "reason": "no_provider"}`` and the
DETERMINISTIC roadmap (the working baseline, produced by ``select_target_role``)
is left COMPLETELY INTACT — no fake roadmap is ever written. The API surfaces this
as a loud 503.

A configured provider (Module 10) drafts an enriched, still-ADVISORY tiered path
and locks a NEW ``source=AI`` roadmap as a DRAFT (advisory, never auto-promotion);
the human accepts it before it becomes ACTIVE. The deterministic baseline is never
overwritten.
"""
import logging

from celery import shared_task

from apps.tenancy.context import tenant_context

from . import engine, services
from .models import DevelopmentRoadmap
from .roadmap_agent import CareerRoadmapNotConfiguredError, get_provider

logger = logging.getLogger("pms.career.roadmap_agent")


def _resolve_target(target_ref):
    """Resolve a ``target_ref`` ({"jd": id} | {"position": id}) to a
    ``(JobDescription|None, Position|None)`` pair through the tenant-scoped
    managers (caller is inside ``tenant_context``)."""
    from apps.jd.models import JobDescription
    from apps.org.models import Position

    jd = pos = None
    if target_ref.get("jd"):
        jd = JobDescription.objects.filter(id=target_ref["jd"]).first()
    elif target_ref.get("position"):
        pos = Position.objects.filter(id=target_ref["position"]).first()
    return jd, pos


@shared_task
def generate_roadmap(tenant_id, employee_id, target_ref, actor_id=None):
    """Enrich ``employee_id``'s roadmap toward ``target_ref`` with the Career
    Roadmap agent, HITL-gated. Returns a summary dict; ``{"generated": False, ...}``
    on any skip — the deterministic baseline is never mutated on a skip path."""
    from apps.identity.models import User

    with tenant_context(tenant_id):
        employee = User.objects.filter(id=employee_id).first()
        if employee is None:
            logger.warning(
                "Career enrich skipped for tenant=%s: employee=%s not found.",
                tenant_id,
                employee_id,
            )
            return {"generated": False, "reason": "employee_not_found"}

        target_jd, target_position = _resolve_target(target_ref or {})
        if target_jd is None and target_position is None:
            logger.warning(
                "Career enrich skipped for tenant=%s employee=%s: target not found.",
                tenant_id,
                employee_id,
            )
            return {"generated": False, "reason": "target_not_found"}

        # The deterministic gap is computed ALWAYS — it is the agent's input and the
        # baseline is core, not faked. We do NOT mutate the existing deterministic
        # roadmap here (it stays completely intact on every skip path).
        gap = engine.compute_skill_gap(employee.id)

        provider = get_provider()
        if not getattr(provider, "configured", False):
            logger.warning(
                "Career enrich skipped for tenant=%s employee=%s: no Career Roadmap "
                "agent configured (lands in Module 10); deterministic roadmap intact.",
                tenant_id,
                employee_id,
            )
            return {"generated": False, "reason": "no_provider"}

        if actor_id is None:
            logger.warning(
                "Career enrich refused for tenant=%s employee=%s: no actor_id; an "
                "accountable human requester is required.",
                tenant_id,
                employee_id,
            )
            return {"generated": False, "reason": "actor_required"}

        actor = User.objects.filter(id=actor_id).first()
        if actor is None:
            return {"generated": False, "reason": "actor_not_found"}

        label = services.target_label_for(target_jd, target_position)
        baseline = (
            DevelopmentRoadmap.objects.filter(
                employee=employee,
                target_jd=target_jd,
                target_position=target_position,
                source=DevelopmentRoadmap.Source.DETERMINISTIC,
            )
            .order_by("-generated_at")
            .first()
        )
        baseline_tiers = baseline.tiers if baseline else engine.build_roadmap_tiers(
            gap, target_label=label
        )

        try:
            result = provider.draft(
                employee_id=str(employee.id),
                target_label=label,
                gap=gap,
                baseline_tiers=baseline_tiers,
            )
        except CareerRoadmapNotConfiguredError:
            logger.warning(
                "Career enrich skipped for tenant=%s employee=%s: provider reported "
                "not configured; deterministic roadmap intact.",
                tenant_id,
                employee_id,
            )
            return {"generated": False, "reason": "no_provider"}
        except Exception as exc:  # noqa: BLE001 - a provider bug must not crash the worker
            reason = (
                "budget_exceeded"
                if getattr(exc, "gateway_status", None) == "BUDGET_EXCEEDED"
                else "provider_error"
            )
            logger.error(
                "Career Roadmap provider failed for tenant=%s employee=%s; "
                "deterministic roadmap left intact for ops to inspect.",
                tenant_id,
                employee_id,
                exc_info=True,
            )
            return {"generated": False, "reason": reason}

        # A NEW AI roadmap, locked as a DRAFT (advisory, never auto-promotion) for
        # the human to accept — the deterministic baseline is never overwritten.
        from apps.audit.services import record
        from django.utils import timezone

        record(
            action="career.roadmap_ai_drafted",
            actor=actor,
            target_type="development_roadmap",
            target_id="",
            metadata={"employee": str(employee.id), "source": "AI"},
            tenant=tenant_id,
        )
        ai_roadmap = DevelopmentRoadmap.objects.create(
            tenant_id=tenant_id,
            employee=employee,
            target_jd=target_jd,
            target_position=target_position,
            status=DevelopmentRoadmap.Status.DRAFT,
            tiers=result["tiers"],
            skill_gap=gap,
            source=DevelopmentRoadmap.Source.AI,
            advisory=True,
            confidence_score=result.get("confidence_score"),
            generated_at=timezone.now(),
            generated_by=actor,
        )
        return {
            "generated": True,
            "roadmap_id": str(ai_roadmap.id),
            "status": ai_roadmap.status,
        }
