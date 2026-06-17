"""
Audit Console serializers.

``AuditLogSerializer`` is the READ-ONLY output for the audit console. The audit
log is append-only and immutable (Module-1 architecture rule 5), so every field
is read-only and there is deliberately no write surface here — the console only
ever reads.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.core.display import person_label

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    """Read-only projection of an :class:`~apps.audit.models.AuditLog` row.

    ``actor`` is the acting user (null for system actions); ``actor_name`` is the
    resolved human label so the console never shows a raw actor uuid. ``target_*``
    is a TYPED object reference (target_type + the entity id) — not a person — and
    the UI renders it as "<type> #<short-id>", not as a name.
    """

    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "actor",
            "actor_name",
            "action",
            "target_type",
            "target_id",
            "justification",
            "metadata",
            "created_at",
        ]
        read_only_fields = fields

    def get_actor_name(self, obj) -> str | None:
        return person_label(obj.actor) if obj.actor_id else None
