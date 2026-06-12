"""
Career Development serializers — SHAPE only; behaviour lives in the services
(``services.py``), the deterministic engine (``engine.py``) and the Career Roadmap
agent seam (``tasks.py``).

Every state-stamped field is mutated EXCLUSIVELY by a service write — the read
serializers mark everything read-only and the input serializers carry ONLY the
client-supplied inputs, with deliberately NO update serializer (no PATCH/PUT path
exists; selection / regenerate / progress go through their own POSTs).

``tenant``, ``selected_by`` / ``generated_by`` / ``updated_by`` and every timestamp
are NEVER client-supplied: the services stamp the tenant from the actor's bound
request and the accountable human from the authenticated caller. The referenced
users / JDs / positions are carried as bare UUIDs and resolved by the view through
their TENANT-SCOPED managers so a cross-tenant id 404s (never a 400 that leaks
existence).

THE DATA BOUNDARY (the headline safety property of Module 9): a career response
carries ONLY the employee's own performance-derived gap (performance band, weak
goal categories) + advisory tiers. These serializers deliberately expose NO
succession surface (readiness / potential band / bench / coverage / 9-box) and no
other employee's data — the engine already guarantees this, and the read shapes
below add nothing back.
"""
from __future__ import annotations

from rest_framework import serializers

from .models import DevelopmentRoadmap, RoadmapProgress, TargetRoleSelection


# ── read-only output shapes ───────────────────────────────────────────────────


class DevelopmentRoadmapSerializer(serializers.ModelSerializer):
    """Read-only output shape for a :class:`DevelopmentRoadmap`. ``advisory`` is
    always True (DB CHECK enforced); ``tiers`` + ``skill_gap`` come from the
    deterministic engine. NO succession fields are exposed — the response carries
    only the employee's own performance-derived gap + advisory tiers."""

    class Meta:
        model = DevelopmentRoadmap
        fields = [
            "id",
            "employee",
            "target_jd",
            "target_position",
            "selection",
            "status",
            "tiers",
            "skill_gap",
            "source",
            "advisory",
            "confidence_score",
            "generated_at",
            "generated_by",
        ]
        read_only_fields = fields


class TargetRoleSelectionSerializer(serializers.ModelSerializer):
    """Read-only output shape for a :class:`TargetRoleSelection`. ``selected_by`` +
    ``selected_at`` are server-set by the service, never through this serializer."""

    class Meta:
        model = TargetRoleSelection
        fields = [
            "id",
            "employee",
            "target_jd",
            "target_position",
            "selected_by",
            "selected_at",
        ]
        read_only_fields = fields


class RoadmapProgressSerializer(serializers.ModelSerializer):
    """Read-only output shape for a :class:`RoadmapProgress` row. The status is set
    only through ``services.set_progress``; ``updated_by`` is server-stamped."""

    class Meta:
        model = RoadmapProgress
        fields = ["id", "roadmap", "tier_index", "status", "updated_by"]
        read_only_fields = fields


# ── input shapes (client-supplied inputs only) ────────────────────────────────


class TargetSelectSerializer(serializers.Serializer):
    """Inputs for ``POST /api/career/target``: an optional ``employee`` (defaults to
    the caller; resolved by the view through the tenant-scoped manager → 404) and a
    target — EXACTLY ONE of ``target_jd`` / ``target_position`` (service-validated,
    422 otherwise; a target JD must be PUBLISHED). ``selected_by`` / timestamps /
    tenant are server-set, so absent here. The UUIDs are resolved by the view
    through the tenant-scoped managers (cross-tenant id → 404)."""

    employee = serializers.UUIDField(required=False, allow_null=True, default=None)
    target_jd = serializers.UUIDField(required=False, allow_null=True, default=None)
    target_position = serializers.UUIDField(
        required=False, allow_null=True, default=None
    )


class ProgressSerializer(serializers.Serializer):
    """Body for ``POST /api/career/roadmaps/<pk>/progress``: the tier to mark + its
    new status. An out-of-range ``tier_index`` is rejected (422) in the service."""

    tier_index = serializers.IntegerField(min_value=0)
    status = serializers.ChoiceField(choices=RoadmapProgress.Status.choices)
