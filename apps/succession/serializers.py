"""
Succession serializers — SHAPE only; behaviour lives in the services
(``services.py``), the plan HITL (``plans.py``) and the Agent-4 seam
(``tasks.py``).

Succession is the MOST SENSITIVE data in the system, so every state-stamped field
is mutated EXCLUSIVELY by a service / plan write — the read serializers mark
everything read-only and the input serializers carry ONLY the client-supplied
inputs, with deliberately NO update serializer (no PATCH path exists; state
changes go through mark / knowledge-risk / archive / readiness / assess / generate
/ action-item / publish).

``tenant``, ``actor`` (marked_by / added_by / assessed_by / reviewed_by) and every
timestamp are NEVER client-supplied: the services stamp the tenant from the
actor's bound request and the accountable human from the authenticated caller. The
referenced users / positions / cycles are carried as bare UUIDs and resolved by
the view through their TENANT-SCOPED managers so a cross-tenant id 404s (never a
400 that leaks existence).

The dashboard endpoint returns a plain dict straight from ``plans.dashboard`` —
there is no serializer for it.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.core.display import person_label

from .models import BenchCandidate, CriticalRole, NineBoxPlacement, SuccessionPlan


# ── read-only output shapes ───────────────────────────────────────────────────


class CriticalRoleSerializer(serializers.ModelSerializer):
    """Read-only output shape for a :class:`CriticalRole`. Every mutation goes
    through a ``services`` write (mark / knowledge-risk / archive), never through
    this serializer."""

    incumbent_name = serializers.SerializerMethodField()

    class Meta:
        model = CriticalRole
        fields = [
            "id",
            "name",
            "position",
            "incumbent",
            "incumbent_name",
            "criticality",
            "knowledge_risk",
            "risk_notes",
            "marked_by",
            "status",
            "created_at",
        ]
        read_only_fields = fields

    def get_incumbent_name(self, obj) -> str | None:
        # Management-only module (employees 404 on all of it); resolving the
        # incumbent within the caller's scope is allowed.
        return person_label(obj.incumbent) if obj.incumbent_id else None


class BenchCandidateSerializer(serializers.ModelSerializer):
    """Read-only output shape for a :class:`BenchCandidate`. Readiness is seeded
    by the engine and overridden only through ``services.set_readiness``."""

    candidate_name = serializers.SerializerMethodField()

    class Meta:
        model = BenchCandidate
        fields = [
            "id",
            "critical_role",
            "candidate",
            "candidate_name",
            "readiness",
            "readiness_overridden",
            "notes",
            "added_by",
            "created_at",
        ]
        read_only_fields = fields

    def get_candidate_name(self, obj) -> str | None:
        return person_label(obj.candidate) if obj.candidate_id else None


class NineBoxSerializer(serializers.ModelSerializer):
    """Read-only output shape for a :class:`NineBoxPlacement`. Performance band +
    box are DERIVED by the engine; only the potential band is human-assigned (via
    ``services.assess_nine_box``)."""

    employee_name = serializers.SerializerMethodField()
    #: The cell to DISPLAY: the human override when set, else the computed box.
    effective_box = serializers.SerializerMethodField()
    is_overridden = serializers.SerializerMethodField()

    class Meta:
        model = NineBoxPlacement
        fields = [
            "id",
            "employee",
            "employee_name",
            "cycle",
            "performance_band",
            "potential_band",
            "box",
            "assessed_by",
            "assessed_at",
            # Human override of the computed box (HRBP/Admin); computed `box` kept.
            "override_box",
            "override_by",
            "override_at",
            "override_rationale",
            "effective_box",
            "is_overridden",
        ]
        read_only_fields = fields

    def get_employee_name(self, obj) -> str | None:
        return person_label(obj.employee) if obj.employee_id else None

    def get_effective_box(self, obj) -> int:
        return obj.override_box if obj.override_box is not None else obj.box

    def get_is_overridden(self, obj) -> bool:
        return obj.override_box is not None


class SuccessionPlanSerializer(serializers.ModelSerializer):
    """Read-only output shape for a :class:`SuccessionPlan`. The HITL state machine
    (generate / action-item / publish) lives in ``plans.py``; Agent-4 enrichment
    in ``tasks.py``. Never mutated through this serializer."""

    class Meta:
        model = SuccessionPlan
        fields = [
            "id",
            "critical_role",
            "status",
            "ranked_bench",
            "coverage_status",
            "red_flags",
            "action_items",
            "source",
            "confidence_score",
            "generated_at",
            "reviewed_by",
            "published_at",
        ]
        read_only_fields = fields


# ── input shapes (client-supplied inputs only) ────────────────────────────────


class CriticalRoleCreateSerializer(serializers.Serializer):
    """Inputs for ``POST /api/succession/critical-roles``: the role name, an
    optional Position + incumbent to link, and the criticality / knowledge-risk
    flags. ``marked_by`` / ``status`` / tenant are server-set, so absent here. The
    ``position`` / ``incumbent`` UUIDs are resolved by the view through the
    tenant-scoped managers (cross-tenant id → 404)."""

    name = serializers.CharField()
    position = serializers.UUIDField(required=False, allow_null=True, default=None)
    incumbent = serializers.UUIDField(required=False, allow_null=True, default=None)
    criticality = serializers.ChoiceField(
        choices=CriticalRole.Criticality.choices, required=False, default=None
    )
    knowledge_risk = serializers.ChoiceField(
        choices=CriticalRole.KnowledgeRisk.choices, required=False, default=None
    )
    risk_notes = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default=""
    )


class KnowledgeRiskSerializer(serializers.Serializer):
    """Body for ``POST /api/succession/critical-roles/<pk>/knowledge-risk``: the
    new knowledge-risk flag and optional notes. The service stamps the actor."""

    knowledge_risk = serializers.ChoiceField(choices=CriticalRole.KnowledgeRisk.choices)
    risk_notes = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default=None
    )


class BenchAddSerializer(serializers.Serializer):
    """Body for ``POST /api/succession/critical-roles/<pk>/bench``: the candidate id
    to add (a bare UUID resolved by the view through the tenant-scoped manager so a
    cross-tenant id 404s; an out-of-tier candidate 404s in the service) + optional
    notes."""

    candidate = serializers.UUIDField()
    notes = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default=""
    )


class ReadinessSerializer(serializers.Serializer):
    """Body for ``POST /api/succession/bench/<pk>/readiness``: the readiness to set
    (an HRBP/Manager override that STICKS — a re-generate never recomputes it)."""

    readiness = serializers.ChoiceField(choices=BenchCandidate.Readiness.choices)


class NineBoxAssessSerializer(serializers.Serializer):
    """Body for ``POST /api/succession/nine-box``: the employee + cycle to place and
    the HUMAN-assigned potential band. The performance band + box are DERIVED in the
    engine. The ``employee`` / ``cycle`` UUIDs are resolved by the view through the
    tenant-scoped managers (cross-tenant id → 404; out-of-tier employee → 404)."""

    employee = serializers.UUIDField()
    cycle = serializers.UUIDField()
    potential_band = serializers.ChoiceField(choices=NineBoxPlacement.Band.choices)


class ActionItemSerializer(serializers.Serializer):
    """Body for ``POST /api/succession/plans/<pk>/action-item``: the action-item
    text an HRBP adds during review (the actor is server-set)."""

    item = serializers.CharField()
