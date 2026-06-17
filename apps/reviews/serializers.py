"""
Review serializers — SHAPE only; behaviour lives elsewhere.

A review's state and every state-stamped field (``state``, ``human_reviewer``,
``approved_at``, ``finalized_at``, ``final_body``, ``rejected_reason``,
``source``, AI fields) are mutated EXCLUSIVELY by the state machine
(``state_machine.py``) and the services (``services.py``) — so the read
serializer marks everything read-only, the create serializer carries only the
creation inputs, and there is deliberately NO update serializer (no PATCH path
exists; ``draft_body`` is written via the submit transition).

``tenant`` is never accepted or echoed: the services stamp it from the subject /
the bound request tenant.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.core.display import person_label

from .models import Review, ReviewAssessment, ReviewStateTransition


class ReviewSerializer(serializers.ModelSerializer):
    """Read-only output shape for a :class:`Review`. Every mutation goes through
    ``create_review`` or a state-machine transition, never through this
    serializer. Person/cycle FKs carry a resolved ``*_name`` label next to the id
    so the UI never renders a raw uuid (the ids stay for React keys/links)."""

    employee_name = serializers.SerializerMethodField()
    reviewer_name = serializers.SerializerMethodField()
    human_reviewer_name = serializers.SerializerMethodField()
    cycle_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id",
            "employee",
            "employee_name",
            "reviewer",
            "reviewer_name",
            "cycle",
            "cycle_name",
            "state",
            "draft_body",
            "final_body",
            "human_reviewer",
            "human_reviewer_name",
            "approved_at",
            "finalized_at",
            "rejected_reason",
            "source",
            "confidence_score",
            "citations",
            "created_at",
        ]
        read_only_fields = fields

    def get_employee_name(self, obj) -> str | None:
        return person_label(obj.employee)

    def get_reviewer_name(self, obj) -> str | None:
        return person_label(obj.reviewer)

    def get_human_reviewer_name(self, obj) -> str | None:
        return person_label(obj.human_reviewer)

    def get_cycle_name(self, obj) -> str | None:
        return obj.cycle.name if obj.cycle_id else None


class ReviewCreateSerializer(serializers.Serializer):
    """Inputs for ``POST /api/reviews/``: the subject, the cycle, and an
    optional initial draft. Plain UUIDs here — the view resolves them through
    the TENANT-SCOPED managers so a cross-tenant id 404s (never a 400 that
    leaks existence)."""

    employee = serializers.UUIDField()
    cycle = serializers.UUIDField()
    draft_body = serializers.CharField(required=False, allow_blank=True, default="")


class AssessmentSerializer(serializers.ModelSerializer):
    """Read/write shape for a :class:`ReviewAssessment`.

    ``assessor`` is always the authenticated caller and ``submitted_at`` is
    always SERVER time (stamped by ``submit_assessment``) — both read-only, so
    a client can neither impersonate an assessor nor backdate a submission.
    """

    assessor_name = serializers.SerializerMethodField()

    class Meta:
        model = ReviewAssessment
        fields = ["id", "assessor", "assessor_name", "assessment_type", "body", "submitted_at"]
        read_only_fields = ["id", "assessor", "assessor_name", "submitted_at"]

    def get_assessor_name(self, obj) -> str | None:
        return person_label(obj.assessor)


class TransitionSerializer(serializers.ModelSerializer):
    """Read-only timeline row (the approval tracker) for a review. ``actor`` is
    null for system transitions; ``actor_name`` resolves the human label."""

    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = ReviewStateTransition
        fields = ["from_state", "to_state", "actor", "actor_name", "at", "note"]
        read_only_fields = fields

    def get_actor_name(self, obj) -> str | None:
        return person_label(obj.actor)


class CalibrationRowSerializer(serializers.ModelSerializer):
    """One row of the calibration read view (HRBP/Admin, tenant-wide).

    ``final_body`` is exposed only once a review is FINALIZED — in-flight draft
    text stays out of the calibration table. Flagging/adjustment arrives with
    the later calibration write path; this is deliberately read-only.
    """

    final_body = serializers.SerializerMethodField()
    employee_name = serializers.SerializerMethodField()
    reviewer_name = serializers.SerializerMethodField()
    human_reviewer_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id",
            "employee",
            "employee_name",
            "reviewer",
            "reviewer_name",
            "cycle",
            "state",
            "source",
            "confidence_score",
            "human_reviewer",
            "human_reviewer_name",
            "approved_at",
            "finalized_at",
            "final_body",
        ]
        read_only_fields = fields

    def get_final_body(self, obj) -> str | None:
        return obj.final_body if obj.state == Review.State.FINALIZED else None

    def get_employee_name(self, obj) -> str | None:
        return person_label(obj.employee)

    def get_reviewer_name(self, obj) -> str | None:
        return person_label(obj.reviewer)

    def get_human_reviewer_name(self, obj) -> str | None:
        return person_label(obj.human_reviewer)
