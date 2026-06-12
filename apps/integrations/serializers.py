"""
Integration serializers — SHAPE only. NB: there is NO secret field anywhere — the
read shape exposes only the non-secret config + the ``secret_ref`` (an env-var
NAME, not a value), and the input shape accepts the same. The token is resolved
from the environment at use time and never crosses this boundary.
"""
from __future__ import annotations

from rest_framework import serializers

from .models import TenantIntegration


class TenantIntegrationSerializer(serializers.ModelSerializer):
    """Read-only output: kind, enabled, non-secret config, and the secret_ref NAME.
    Deliberately exposes NO token/secret value."""

    class Meta:
        model = TenantIntegration
        fields = ["id", "kind", "enabled", "config", "secret_ref", "updated_at"]
        read_only_fields = fields


class IntegrationUpsertSerializer(serializers.Serializer):
    """Input for PUT: enable/disable + non-secret config + the env-var NAME holding
    the token. A raw token is NEVER accepted here."""

    enabled = serializers.BooleanField(default=False)
    config = serializers.DictField(required=False, default=dict)
    secret_ref = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=128
    )
