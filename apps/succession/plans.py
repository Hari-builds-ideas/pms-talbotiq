"""
SuccessionPlan HITL — generate (deterministic) -> PENDING_HUMAN_REVIEW -> HRBP
reviews + adds action items -> publish to the dashboard.

Mirrors the Agent-4 node sequence, run deterministically now: the plan is locked
PENDING_HUMAN_REVIEW the moment it is generated, and CANNOT be published without
passing through review (an illegal transition is 409). Every step audits BEFORE
the effect. Generate + publish are HRBP/Admin (gated at the view); the dashboard
read is scope-filtered for Managers (own report tier only).
"""
from __future__ import annotations

from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.audit.services import record
from apps.tenancy.context import tenant_context

from . import engine, services
from .exceptions import IllegalPlanTransition
from .models import SuccessionPlan


def generate_plan(actor, critical_role) -> SuccessionPlan:
    """Run the deterministic analysis and lock a new plan PENDING_HUMAN_REVIEW."""
    tid = actor.tenant_id
    with tenant_context(tid):
        analysis = engine.compute_analysis(critical_role)
        record(
            action="plan.generated",
            actor=actor,
            target_type="succession_plan",
            target_id="",
            metadata={
                "critical_role": str(critical_role.id),
                "coverage_status": analysis["coverage_status"],
                "candidates": len(analysis["ranked_bench"]),
            },
            tenant=tid,
        )
        return SuccessionPlan.objects.create(
            tenant_id=tid,
            critical_role=critical_role,
            status=SuccessionPlan.Status.PENDING_HUMAN_REVIEW,
            ranked_bench=analysis["ranked_bench"],
            coverage_status=analysis["coverage_status"],
            red_flags=analysis["red_flags"],
            action_items=[],
            source=SuccessionPlan.Source.DETERMINISTIC,
            generated_at=timezone.now(),
        )


def add_action_item(actor, plan, item) -> SuccessionPlan:
    """Append an HRBP action item during review (plan must be PENDING_HUMAN_REVIEW)."""
    if plan.status != SuccessionPlan.Status.PENDING_HUMAN_REVIEW:
        raise IllegalPlanTransition(plan.status, "add an action item to")
    with tenant_context(plan.tenant_id):
        record(
            action="plan.action_item_added",
            actor=actor,
            target_type="succession_plan",
            target_id=plan.id,
            metadata={"item": item},
            tenant=plan.tenant_id,
        )
        items = list(plan.action_items or [])
        items.append({"text": item, "added_by": str(actor.id)})
        plan.action_items = items
        plan.save(update_fields=["action_items", "updated_at"])
        return plan


def publish_plan(actor, plan) -> SuccessionPlan:
    """PENDING_HUMAN_REVIEW -> PUBLISHED (to the dashboard). A plan that has not
    been through review cannot be published (409)."""
    if plan.status != SuccessionPlan.Status.PENDING_HUMAN_REVIEW:
        raise IllegalPlanTransition(plan.status, "publish")
    with tenant_context(plan.tenant_id):
        record(
            action="plan.published",
            actor=actor,
            target_type="succession_plan",
            target_id=plan.id,
            metadata={"coverage_status": plan.coverage_status},
            tenant=plan.tenant_id,
        )
        plan.status = SuccessionPlan.Status.PUBLISHED
        plan.reviewed_by = actor
        plan.published_at = timezone.now()
        plan.save(update_fields=["status", "reviewed_by", "published_at", "updated_at"])
        return plan


def get_plan_in_scope(actor, plan_id) -> SuccessionPlan:
    """Load a plan whose critical role the actor may see, else 404."""
    plan = SuccessionPlan.objects.filter(id=plan_id).select_related("critical_role").first()
    if plan is None or not services._critical_role_in_scope(actor, plan.critical_role):
        raise NotFound("No such succession plan in your scope.")
    return plan


def dashboard(actor) -> dict:
    """The succession dashboard, scoped: HRBP/Admin see the tenant; a Manager sees
    only critical roles touching their reporting tier. Each role carries its latest
    PUBLISHED plan's coverage (if any)."""
    roles = services.list_critical_roles(actor)
    role_ids = [r.id for r in roles]
    latest_published = {}
    for plan in (
        SuccessionPlan.objects.filter(
            critical_role_id__in=role_ids, status=SuccessionPlan.Status.PUBLISHED
        ).order_by("-published_at")
    ):
        latest_published.setdefault(plan.critical_role_id, plan)

    return {
        "critical_roles": [
            {
                "id": str(r.id),
                "name": r.name,
                "criticality": r.criticality,
                "knowledge_risk": r.knowledge_risk,
                "status": r.status,
                "coverage_status": (
                    latest_published[r.id].coverage_status if r.id in latest_published else None
                ),
                "published_plan": (
                    str(latest_published[r.id].id) if r.id in latest_published else None
                ),
            }
            for r in roles
        ],
    }
