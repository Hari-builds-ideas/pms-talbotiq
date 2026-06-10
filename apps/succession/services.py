"""
Succession services — the scope-enforcing, audited mutators + scoped reads.

SENSITIVITY: succession data is management-only. Every read/write here is scoped:
HRBP/Admin see the whole tenant; a Manager is confined to their reporting subtree
(``reporting_subtree_ids`` + self). A scope miss raises ``NotFound`` (404), never
a 403 — the module must not leak the existence of out-of-tier data. (Employees
are blocked at the permission layer with a 404 before they ever reach a service.)

Every consequential write audits BEFORE it takes effect and binds the tenant
explicitly (off-request safe).
"""
from __future__ import annotations

from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.audit.services import record
from apps.identity.models import User
from apps.goals.models import CycleScore
from apps.rbac.scope import Scope, actor_can_access, reporting_subtree_ids, scope_for_role
from apps.tenancy.context import tenant_context

from . import constants as C, engine
from .models import BenchCandidate, CriticalRole, NineBoxPlacement


# ── scope helpers ─────────────────────────────────────────────────────────────


def require_in_scope(actor, target_user):
    """Raise ``NotFound`` (404) unless ``target_user`` is within ``actor``'s data
    scope (HRBP/Admin = tenant; Manager = reporting subtree). Used to guard a
    per-employee write/read so an out-of-tier target is indistinguishable from a
    non-existent one."""
    if target_user is None or not actor_can_access(actor, target_user):
        raise NotFound("No such succession record in your scope.")


def visible_user_ids(actor) -> set:
    """The set of user ids whose succession data ``actor`` may see: the whole
    active tenant for HRBP/Admin, or the actor's reporting subtree + self for a
    Manager. (Employees never reach here — the permission layer 404s them.)"""
    if scope_for_role(actor.role) is Scope.TENANT:
        return set(User.objects.filter(is_active=True).values_list("id", flat=True))
    return reporting_subtree_ids(actor) | {actor.id}


def _critical_role_in_scope(actor, critical_role) -> bool:
    """A Manager sees a critical role only if its incumbent OR any bench candidate
    is within their reporting subtree; HRBP/Admin see all."""
    if scope_for_role(actor.role) is Scope.TENANT:
        return True
    visible = visible_user_ids(actor)
    if critical_role.incumbent_id and critical_role.incumbent_id in visible:
        return True
    return critical_role.bench.filter(candidate_id__in=visible).exists()


def get_critical_role_in_scope(actor, role_id) -> CriticalRole:
    """Load a critical role the actor may see, else 404."""
    role = CriticalRole.objects.filter(id=role_id).first()
    if role is None or not _critical_role_in_scope(actor, role):
        raise NotFound("No such critical role in your scope.")
    return role


# ── critical-role registry (HRBP/Admin — gated at the view) ───────────────────


def mark_critical_role(actor, *, name, position=None, incumbent=None,
                       criticality=None, knowledge_risk=None, risk_notes=""):
    """Register a critical role with its knowledge-risk flag."""
    tid = actor.tenant_id
    with tenant_context(tid):
        record(
            action="critical_role.marked",
            actor=actor,
            target_type="critical_role",
            target_id="",
            metadata={"name": name, "criticality": criticality},
            tenant=tid,
        )
        return CriticalRole.objects.create(
            tenant_id=tid,
            name=name,
            position=position,
            incumbent=incumbent,
            criticality=criticality or CriticalRole.Criticality.HIGH,
            knowledge_risk=knowledge_risk or CriticalRole.KnowledgeRisk.LOW,
            risk_notes=risk_notes or "",
            marked_by=actor,
            status=CriticalRole.Status.ACTIVE,
        )


def update_knowledge_risk(actor, critical_role, *, knowledge_risk, risk_notes=None):
    """Update a role's knowledge-risk flag (and optionally the notes)."""
    with tenant_context(critical_role.tenant_id):
        record(
            action="critical_role.risk_updated",
            actor=actor,
            target_type="critical_role",
            target_id=critical_role.id,
            metadata={"knowledge_risk": knowledge_risk},
            tenant=critical_role.tenant_id,
        )
        critical_role.knowledge_risk = knowledge_risk
        if risk_notes is not None:
            critical_role.risk_notes = risk_notes
        critical_role.save(update_fields=["knowledge_risk", "risk_notes", "updated_at"])
        return critical_role


def archive_critical_role(actor, critical_role):
    with tenant_context(critical_role.tenant_id):
        record(
            action="critical_role.archived",
            actor=actor,
            target_type="critical_role",
            target_id=critical_role.id,
            metadata={},
            tenant=critical_role.tenant_id,
        )
        critical_role.status = CriticalRole.Status.ARCHIVED
        critical_role.save(update_fields=["status", "updated_at"])
        return critical_role


def list_critical_roles(actor):
    """Critical roles within the actor's scope."""
    roles = CriticalRole.objects.all()
    if scope_for_role(actor.role) is Scope.TENANT:
        return list(roles)
    return [r for r in roles if _critical_role_in_scope(actor, r)]


# ── bench (HRBP/Admin tenant ; Manager own tier) ──────────────────────────────


def add_bench_candidate(actor, critical_role, candidate, *, notes=""):
    """Add ``candidate`` to ``critical_role``'s bench, seeding the deterministic
    readiness. The candidate must be within the actor's scope (else 404)."""
    require_in_scope(actor, candidate)
    tid = actor.tenant_id
    with tenant_context(tid):
        readiness = engine.computed_readiness_for(candidate.id)
        record(
            action="bench.added",
            actor=actor,
            target_type="bench_candidate",
            target_id="",
            metadata={"critical_role": str(critical_role.id), "candidate": str(candidate.id)},
            tenant=tid,
        )
        return BenchCandidate.objects.create(
            tenant_id=tid,
            critical_role=critical_role,
            candidate=candidate,
            readiness=readiness,
            readiness_overridden=False,
            notes=notes or "",
            added_by=actor,
        )


def set_readiness(actor, bench_candidate, readiness):
    """HRBP/Manager override of a candidate's readiness — STICKS (a re-generate
    will not recompute it). The candidate must be within the actor's scope."""
    require_in_scope(actor, bench_candidate.candidate)
    with tenant_context(bench_candidate.tenant_id):
        record(
            action="readiness.set",
            actor=actor,
            target_type="bench_candidate",
            target_id=bench_candidate.id,
            metadata={"readiness": readiness},
            tenant=bench_candidate.tenant_id,
        )
        bench_candidate.readiness = readiness
        bench_candidate.readiness_overridden = True
        bench_candidate.save(update_fields=["readiness", "readiness_overridden", "updated_at"])
        return bench_candidate


def list_bench(actor, critical_role):
    """A role's bench, scoped: HRBP/Admin see all; a Manager sees only candidates
    within their reporting subtree."""
    qs = critical_role.bench.select_related("candidate")
    if scope_for_role(actor.role) is Scope.TENANT:
        return list(qs)
    visible = visible_user_ids(actor)
    return [bc for bc in qs if bc.candidate_id in visible]


# ── 9-box (HRBP/Admin tenant ; Manager own tier) ──────────────────────────────


def _perf_band_for_ninebox(employee_id, cycle_id) -> str:
    """Performance band for a 9-box cell: from the CycleScore for (employee,
    cycle), else the employee's latest CycleScore, else LOW (unscored)."""
    score = CycleScore.objects.filter(employee_id=employee_id, cycle_id=cycle_id).first()
    if score is None:
        score = engine.latest_cyclescore(employee_id)
    band = engine.performance_band_from_tscore(score.t_score) if score else C.BAND_UNKNOWN
    return C.BAND_LOW if band == C.BAND_UNKNOWN else band


def assess_nine_box(actor, employee, cycle, *, potential_band):
    """Place ``employee`` on the 9-box for ``cycle``: performance band DERIVED from
    their CycleScore, potential band HUMAN-assigned. Upserts (unique per employee+
    cycle). The employee must be within the actor's scope (else 404)."""
    require_in_scope(actor, employee)
    tid = actor.tenant_id
    with tenant_context(tid):
        performance_band = _perf_band_for_ninebox(employee.id, cycle.id)
        box = engine.compute_box(performance_band, potential_band)
        record(
            action="ninebox.assessed",
            actor=actor,
            target_type="ninebox",
            target_id=str(employee.id),
            metadata={
                "cycle": str(cycle.id),
                "performance_band": performance_band,
                "potential_band": potential_band,
                "box": box,
            },
            tenant=tid,
        )
        placement, _created = NineBoxPlacement.objects.update_or_create(
            tenant_id=tid,
            employee=employee,
            cycle=cycle,
            defaults={
                "performance_band": performance_band,
                "potential_band": potential_band,
                "box": box,
                "assessed_by": actor,
                "assessed_at": timezone.now(),
            },
        )
        return placement


def list_nine_box(actor, *, cycle=None):
    """9-box placements within the actor's scope (optionally filtered by cycle)."""
    qs = NineBoxPlacement.objects.all()
    if cycle is not None:
        qs = qs.filter(cycle=cycle)
    if scope_for_role(actor.role) is not Scope.TENANT:
        qs = qs.filter(employee_id__in=visible_user_ids(actor))
    return list(qs)
