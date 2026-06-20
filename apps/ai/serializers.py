"""Serializers for the async AI job surface (BUILD_2)."""
from rest_framework import serializers

from .models import AIJob


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
            "confidence",
            "error_code",
            "created_at",
            "started_at",
            "finished_at",
        ]
        read_only_fields = fields
