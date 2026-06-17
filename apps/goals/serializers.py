"""
Goal-tree serializers.

The shape mirrors the model tree: a ``GoalSerializer`` carries nested, read +
write ``kpis`` (``KpiSerializer``). Domain rules live in the validators
(``apps.goals.validators``) and are invoked here; a django ``ValidationError``
from a validator is re-raised as a DRF ``ValidationError`` so the API returns 400
with the validator's message (this powers the editor's live weight-sum
indicator).

Two weight invariants, both EXACT-Decimal ``= 100.00`` (no float, no tolerance):
  * a goal's KPIs must sum to 100.00 (checked on goal create + on the KPI
    sub-resource endpoints);
  * an employee's ACTIVE goals must sum to 100.00 (enforced by the engine /
    other endpoints — not by a single goal write).

``tenant`` is never accepted or echoed: ``TenantScopedModel.save`` stamps it from
the bound request tenant.
"""
from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from apps.core.display import person_label

from .models import Goal, Kpi, KpiMeasurement, KpiTemplate
from .validators import assert_weights_sum_to_100, validate_target_value


class KpiSerializer(serializers.ModelSerializer):
    """Read/write a :class:`Kpi`. ``target_value`` must be strictly > 0 (the same
    rule the engine relies on to never divide by zero)."""

    class Meta:
        model = Kpi
        fields = [
            "id",
            "goal",
            "name",
            "description",
            "weight",
            "target_value",
            "direction",
            "unit",
            "source",
            "external_ref",
        ]
        read_only_fields = ["id", "goal", "external_ref"]

    def validate_target_value(self, value):
        try:
            validate_target_value(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages)
        return value


class _NestedKpiSerializer(KpiSerializer):
    """KPI as written nested inside a goal create: ``goal`` is supplied by the
    parent, never by the client."""

    class Meta(KpiSerializer.Meta):
        fields = [
            "id",
            "name",
            "description",
            "weight",
            "target_value",
            "direction",
            "unit",
            "source",
        ]
        read_only_fields = ["id"]


class GoalSerializer(serializers.ModelSerializer):
    """Read/write a :class:`Goal` with nested ``kpis``.

    On create the nested KPIs are written in one transaction and their weights
    must sum to EXACTLY 100.00. ``kpi_weight_total`` is a computed read field
    (the current KPI weight sum) that powers the editor's live-sum indicator.
    """

    kpis = _NestedKpiSerializer(many=True, required=False)
    kpi_weight_total = serializers.SerializerMethodField()
    employee_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Goal
        fields = [
            "id",
            "employee",
            "employee_name",
            "cycle",
            "created_by",
            "created_by_name",
            "title",
            "description",
            "objective",
            "weight",
            "status",
            "approved_by",
            "approved_by_name",
            "approved_at",
            "kpis",
            "kpi_weight_total",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "employee_name",
            "created_by",
            "created_by_name",
            "approved_by",
            "approved_by_name",
            "approved_at",
            "created_at",
            "updated_at",
        ]

    def get_employee_name(self, obj) -> str | None:
        return person_label(obj.employee)

    def get_created_by_name(self, obj) -> str | None:
        return person_label(obj.created_by) if obj.created_by_id else None

    def get_approved_by_name(self, obj) -> str | None:
        return person_label(obj.approved_by) if obj.approved_by_id else None

    def get_kpi_weight_total(self, obj) -> Decimal:
        """Sum of this goal's KPI weights — the live indicator's value. Exact
        Decimal; the editor compares it against 100.00."""
        return sum((k.weight for k in obj.kpis.all()), Decimal("0"))

    @transaction.atomic
    def create(self, validated_data):
        """Create the goal and its KPIs in one transaction.

        The KPIs' weights must sum to exactly 100.00; a validator failure rolls
        the whole thing back and surfaces as a 400. ``tenant`` is stamped from
        the bound request tenant; ``created_by`` is set by the view.
        """
        kpis_data = validated_data.pop("kpis", [])
        self._assert_kpi_weights(kpis_data)
        goal = Goal.objects.create(**validated_data)
        for kpi_data in kpis_data:
            Kpi.objects.create(goal=goal, **kpi_data)
        return goal

    def update(self, instance, validated_data):
        """Patch a goal's own fields. Nested KPI editing is done via the KPI
        sub-resource endpoints, so ``kpis`` is ignored here if present."""
        validated_data.pop("kpis", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance

    @staticmethod
    def _assert_kpi_weights(kpis_data):
        """Re-raise the validator's django error as a DRF 400 so the message
        reaches the client / live indicator."""
        weights = [k["weight"] for k in kpis_data]
        try:
            assert_weights_sum_to_100(weights, label="A goal's KPI")
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"kpis": exc.messages})


class KpiMeasurementSerializer(serializers.ModelSerializer):
    """Read-only output for a recorded actual. Writes go through
    :func:`apps.goals.services.record_actual`, never this serializer."""

    class Meta:
        model = KpiMeasurement
        fields = ["id", "kpi", "value", "recorded_at", "recorded_by", "source"]
        read_only_fields = fields


class KpiTemplateSerializer(serializers.ModelSerializer):
    """Read-only output for the role-targeted KPI template catalogue."""

    class Meta:
        model = KpiTemplate
        fields = [
            "id",
            "role",
            "name",
            "description",
            "target_value",
            "direction",
            "unit",
            "default_weight",
        ]
        read_only_fields = fields
