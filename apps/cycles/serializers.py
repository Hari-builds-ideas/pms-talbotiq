"""
Cycle serializers.

``CycleSerializer`` is the read/write shape for the cycle CRUD endpoints
(``MANAGE_CYCLES``). ``CycleScoreSerializer`` is read-only output for the score
read endpoints — the scoring engine is the ONLY writer of those rows, so the API
never accepts a score on input.

Tenant is stamped by ``TenantScopedModel.save`` from the bound request tenant, so
no serializer ever takes or echoes ``tenant``.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.goals.models import CycleScore

from .models import PerformanceCycle


class CycleSerializer(serializers.ModelSerializer):
    """Read/write a :class:`PerformanceCycle`. ``status`` defaults to DRAFT on
    create; ``id``/timestamps are read-only."""

    class Meta:
        model = PerformanceCycle
        fields = ["id", "name", "start_date", "end_date", "status", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        """End date must be on or after start date (mirrors ``model.clean``)."""
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError(
                {"end_date": "end_date must be on or after start_date."}
            )
        return attrs


class CycleScoreSerializer(serializers.ModelSerializer):
    """Read-only view of a computed :class:`CycleScore`. Surfaces the raw / z / t
    scores, the risk + pace signals and the cohort metadata the editor reads."""

    class Meta:
        model = CycleScore
        fields = [
            "id",
            "employee",
            "cycle",
            "raw_score",
            "z_score",
            "t_score",
            "cohort_size",
            "cohort_key",
            "insufficient_cohort",
            "risk_status",
            "pace_behind",
            "computed_at",
        ]
        read_only_fields = fields
