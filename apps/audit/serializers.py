"""
Audit Console serializers.

``AuditLogSerializer`` is the READ-ONLY output for the audit console. The audit
log is append-only and immutable (Module-1 architecture rule 5), so every field
is read-only and there is deliberately no write surface here — the console only
ever reads.
"""
from __future__ import annotations

from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    """Read-only projection of an :class:`~apps.audit.models.AuditLog` row."""

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "actor",
            "action",
            "target_type",
            "target_id",
            "justification",
            "metadata",
            "created_at",
        ]
        read_only_fields = fields
