"""
Career services — the scope-enforcing, audited orchestration over the
deterministic engine.

SCOPE (career is employee-visible, unlike succession): an Employee acts on / sees
ONLY themselves; a Manager covers their reporting subtree; HRBP/Admin the tenant.
A scope miss raises ``NotFound`` (404), never a 403 — a roadmap the actor may not
see is indistinguishable from one that does not exist (the project's no-existence-
leak rule). RBAC capability is gated at the view; row scope is enforced here.

THE DATA BOUNDARY: every gap/roadmap this layer produces comes from the engine,
which reads ONLY the subject's own performance data — never the sensitive
succession surface (see ``engine.py``).

Every consequential write audits BEFORE it takes effect and binds the tenant
explicitly (off-request safe).
"""
from __future__ import annotations

from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.audit.services import record
from apps.identity.models import User
from apps.jd.models import JobDescription
from apps.rbac.scope import Scope, actor_can_access, reporting_subtree_ids, scope_for_role
from apps.tenancy.context import tenant_context

from . import engine
from .exceptions import InvalidCareerInput
from .models import DevelopmentRoadmap, RoadmapProgress, TargetRoleSelection


# ── scope helpers ─────────────────────────────────────────────────────────────


def require_in_scope(actor, employee):
    """Raise ``NotFound`` (404) unless ``employee`` is within ``actor``'s data
    scope (Employee = self; Manager = reporting subtree + self; HRBP/Admin =
    tenant). Hides out-of-scope / cross-tenant targets instead of leaking a 403."""
    if employee is None or not actor_can_access(actor, employee):
        raise NotFound("No such career roadmap in your scope.")


def visible_employee_ids(actor) -> set:
    """The employee ids whose career data ``actor`` may see: self (Employee),
    reporting subtree + self (Manager), or the whole active tenant (HRBP/Admin)."""
    tier = scope_for_role(actor.role)
    if tier is Scope.TENANT:
        return set(User.objects.filter(is_active=True).values_list("id", flat=True))
    if tier is Scope.TEAM:
        return reporting_subtree_ids(actor) | {actor.id}
    return {actor.id}


def get_roadmap_in_scope(actor, roadmap_id) -> DevelopmentRoadmap:
    """Load a roadmap whose employee is within the actor's scope, else 404."""
    roadmap = DevelopmentRoadmap.objects.filter(id=roadmap_id).first()
    if roadmap is None or not actor_can_access(
        actor, _employee_of(roadmap)
    ):
        raise NotFound("No such career roadmap in your scope.")
    return roadmap


def _employee_of(roadmap) -> User | None:
    return User.objects.filter(id=roadmap.employee_id).first()


# ── target resolution ─────────────────────────────────────────────────────────


def target_label_for(target_jd, target_position) -> str:
    if target_jd is not None:
        return f"{target_jd.title} ({target_jd.level})"
    return target_position.title


def _validate_target(target_jd, target_position):
    """Require EXACTLY ONE target; a target JD must be PUBLISHED (you cannot aim at
    a draft/archived role profile). Raises 422 ``InvalidCareerInput`` otherwise."""
    if (target_jd is None) == (target_position is None):
        raise InvalidCareerInput(
            "Provide exactly one of target_jd / target_position.",
            code="TARGET_AMBIGUOUS",
        )
    if target_jd is not None and target_jd.status != JobDescription.Status.PUBLISHED:
        raise InvalidCareerInput(
            "A target job description must be PUBLISHED.", code="TARGET_NOT_PUBLISHED"
        )


# ── select target + deterministic generation ──────────────────────────────────


def select_target_role(actor, employee, *, target_jd=None, target_position=None):
    """Record ``employee``'s target role and generate (or refresh) the deterministic
    development roadmap. Returns ``(selection, roadmap)``. The employee must be in
    the actor's scope (else 404); the target must be valid (else 422)."""
    require_in_scope(actor, employee)
    _validate_target(target_jd, target_position)
    tid = actor.tenant_id
    with tenant_context(tid):
        record(
            action="career.target_selected",
            actor=actor,
            target_type="career_target",
            target_id="",
            metadata={
                "employee": str(employee.id),
                "target_jd": str(target_jd.id) if target_jd else None,
                "target_position": str(target_position.id) if target_position else None,
            },
            tenant=tid,
        )
        selection = TargetRoleSelection.objects.create(
            tenant_id=tid,
            employee=employee,
            target_jd=target_jd,
            target_position=target_position,
            selected_by=actor,
            selected_at=timezone.now(),
        )
        roadmap = _generate_deterministic_roadmap(
            actor,
            employee,
            target_jd=target_jd,
            target_position=target_position,
            selection=selection,
        )
        return selection, roadmap


def _generate_deterministic_roadmap(
    actor, employee, *, target_jd, target_position, selection
) -> DevelopmentRoadmap:
    """Compute the gap + tiers and upsert the single ACTIVE deterministic roadmap
    for (employee, target). Caller is already inside ``tenant_context``. The
    "one ACTIVE per (employee, target)" invariant is enforced here in code."""
    tid = employee.tenant_id
    gap = engine.compute_skill_gap(employee.id)
    label = target_label_for(target_jd, target_position)
    tiers = engine.build_roadmap_tiers(gap, target_label=label)

    record(
        action="career.roadmap_generated",
        actor=actor,
        target_type="development_roadmap",
        target_id="",
        metadata={
            "employee": str(employee.id),
            "performance_band_gap": gap["performance_band_gap"],
            "tiers": len(tiers),
        },
        tenant=tid,
    )

    existing = (
        DevelopmentRoadmap.objects.filter(
            employee=employee,
            target_jd=target_jd,
            target_position=target_position,
            status=DevelopmentRoadmap.Status.ACTIVE,
            source=DevelopmentRoadmap.Source.DETERMINISTIC,
        )
        .order_by("-generated_at")
        .first()
    )
    if existing is not None:
        existing.tiers = tiers
        existing.skill_gap = gap
        existing.generated_at = timezone.now()
        existing.generated_by = actor
        if selection is not None:
            existing.selection = selection
        existing.save(
            update_fields=[
                "tiers",
                "skill_gap",
                "generated_at",
                "generated_by",
                "selection",
                "updated_at",
            ]
        )
        return existing

    return DevelopmentRoadmap.objects.create(
        tenant_id=tid,
        employee=employee,
        target_jd=target_jd,
        target_position=target_position,
        selection=selection,
        status=DevelopmentRoadmap.Status.ACTIVE,
        tiers=tiers,
        skill_gap=gap,
        source=DevelopmentRoadmap.Source.DETERMINISTIC,
        advisory=True,
        generated_at=timezone.now(),
        generated_by=actor,
    )


def regenerate_roadmap(actor, roadmap) -> DevelopmentRoadmap:
    """Refresh a deterministic roadmap's gap + tiers from the employee's current
    performance data (advisory, ungated beyond RBAC + scope). Returns the roadmap.
    """
    employee = _employee_of(roadmap)
    require_in_scope(actor, employee)
    with tenant_context(roadmap.tenant_id):
        return _generate_deterministic_roadmap(
            actor,
            employee,
            target_jd=roadmap.target_jd,
            target_position=roadmap.target_position,
            selection=roadmap.selection,
        )


# ── reads ──────────────────────────────────────────────────────────────────────


def skill_gap_for(actor, employee) -> dict:
    """The live deterministic skill gap for ``employee`` (scoped → 404). Contains
    ONLY the employee's own performance-derived gap — never succession data."""
    require_in_scope(actor, employee)
    with tenant_context(actor.tenant_id):
        return engine.compute_skill_gap(employee.id)


def list_roadmaps(actor, *, employee=None) -> list[DevelopmentRoadmap]:
    """Roadmaps within the actor's scope. With ``employee`` given, that employee's
    roadmaps (scoped → 404); otherwise every visible employee's roadmaps."""
    if employee is not None:
        require_in_scope(actor, employee)
        return list(DevelopmentRoadmap.objects.filter(employee=employee))
    return list(
        DevelopmentRoadmap.objects.filter(employee_id__in=visible_employee_ids(actor))
    )


# ── progress ────────────────────────────────────────────────────────────────────


def set_progress(actor, roadmap, *, tier_index, status) -> RoadmapProgress:
    """Mark a roadmap tier's progress (upsert per roadmap+tier). The roadmap's
    employee must be in scope (else 404); ``tier_index`` must address a real tier
    (else 422)."""
    employee = _employee_of(roadmap)
    require_in_scope(actor, employee)
    if not (0 <= tier_index < len(roadmap.tiers or [])):
        raise InvalidCareerInput(
            f"tier_index {tier_index} is out of range for this roadmap.",
            code="TIER_OUT_OF_RANGE",
        )
    with tenant_context(roadmap.tenant_id):
        record(
            action="career.progress_updated",
            actor=actor,
            target_type="roadmap_progress",
            target_id=str(roadmap.id),
            metadata={"tier_index": tier_index, "status": status},
            tenant=roadmap.tenant_id,
        )
        progress, _created = RoadmapProgress.objects.update_or_create(
            tenant_id=roadmap.tenant_id,
            roadmap=roadmap,
            tier_index=tier_index,
            defaults={"status": status, "updated_by": actor},
        )
        return progress


def list_progress(actor, roadmap) -> list[RoadmapProgress]:
    """A roadmap's per-tier progress rows (the roadmap is already scope-checked by
    the caller via ``get_roadmap_in_scope``)."""
    return list(roadmap.progress.all())
