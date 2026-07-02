"""Serializers for the async AI job surface (BUILD_2) + the agentic chat V2
session/plan surface (OVERNIGHT_A)."""
from rest_framework import serializers

from .models import AIJob, ChatPlan, ChatPlanStep, ChatSession, ChatTurn


class AIJobSerializer(serializers.ModelSerializer):
    """The poll shape for an :class:`AIJob`. Read-only — the client never mutates
    a job; it enqueues (202) then polls this until the status is terminal.

    ``target_id`` is the artifact (Review / FeedbackSummary / ...) the client
    re-fetches once ``status == SUCCEEDED`` to show the PENDING-review draft."""

    class Meta:
        model = AIJob
        fields = [
            "id",
            "status",
            "agent_code",
            "target_type",
            "target_id",
            "result_id",
            "confidence",
            "error_code",
            "created_at",
            "started_at",
            "finished_at",
        ]
        read_only_fields = fields


# ── Agentic chat V2 (OVERNIGHT_A) — session + plan read shapes (all read-only) ──


class ChatPlanStepSerializer(serializers.ModelSerializer):
    """One step of a plan — the checklist item the UI renders (Approve · Skip ·
    Explain). All fields read-only; a step only ever changes via the approve endpoint."""

    class Meta:
        model = ChatPlanStep
        fields = [
            "id", "ordinal", "action", "feel", "summary", "reason", "preview",
            "deeplink", "prefill", "candidates", "status", "result",
        ]
        read_only_fields = fields


class ChatPlanSerializer(serializers.ModelSerializer):
    steps = ChatPlanStepSerializer(many=True, read_only=True)

    class Meta:
        model = ChatPlan
        fields = ["id", "session", "message", "summary", "confidence", "steps", "created_at"]
        read_only_fields = fields


class ChatTurnSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatTurn
        fields = ["id", "role", "text", "refs", "created_at"]
        read_only_fields = fields


class ChatSessionSerializer(serializers.ModelSerializer):
    """The recent-chats list row (no turns)."""

    class Meta:
        model = ChatSession
        fields = ["id", "title", "last_activity", "created_at"]
        read_only_fields = fields


class ChatSessionDetailSerializer(ChatSessionSerializer):
    """A single session WITH its recent turns (the resume payload)."""

    turns = serializers.SerializerMethodField()

    class Meta(ChatSessionSerializer.Meta):
        fields = ChatSessionSerializer.Meta.fields + ["turns"]
        read_only_fields = fields

    def get_turns(self, obj):
        from apps.ai.sessions import recent_turns

        return ChatTurnSerializer(recent_turns(obj), many=True).data
