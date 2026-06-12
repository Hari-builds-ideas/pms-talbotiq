"""
Admin Hub serializers.

Output serializers (``UserAdminSerializer``, ``TenantConfigSerializer``) are
read-only projections; input serializers carry only the client-supplied fields
the services accept. The actor and tenant are ALWAYS server-set (from the JWT) —
they are never accepted from the client — so they never appear on an input
serializer. Referenced UUIDs (a manager, a new reporting manager) are validated
as UUIDs here and resolved to a tenant-scoped row in the view (cross-tenant id →
404).
"""
from __future__ import annotations

from rest_framework import serializers

from apps.identity.models import User

from .models import TenantConfig


# ── output (read-only) ───────────────────────────────────────────────────────


class UserAdminSerializer(serializers.ModelSerializer):
    """Read-only projection of a user for the Admin Hub user list / responses."""

    class Meta:
        model = User
        fields = ["id", "email", "role", "manager", "is_active", "mfa_enabled"]
        read_only_fields = fields


class TenantConfigSerializer(serializers.ModelSerializer):
    """Read-only projection of the tenant's config row."""

    class Meta:
        model = TenantConfig
        fields = ["id", "settings"]
        read_only_fields = fields


# ── input ────────────────────────────────────────────────────────────────────


class CreateUserSerializer(serializers.Serializer):
    """Body for ``POST /users``. ``manager`` is an optional UUID resolved in the
    view to a tenant-scoped ``User`` (cross-tenant id → 404)."""

    email = serializers.EmailField()
    role = serializers.CharField()
    manager = serializers.UUIDField(required=False, allow_null=True, default=None)
    password = serializers.CharField(required=False, allow_null=True, default=None)


class SetRoleSerializer(serializers.Serializer):
    """Body for ``POST /users/<id>/role``."""

    role = serializers.CharField()


class ReportingLineSerializer(serializers.Serializer):
    """Body for ``POST /users/<id>/reporting-line``. ``manager`` is the new
    manager's UUID, resolved in the view to a tenant-scoped ``User``."""

    manager = serializers.UUIDField()


class TenantConfigUpdateSerializer(serializers.Serializer):
    """Body for ``PUT /tenant-config``: the full ``settings`` bag (a JSON object)."""

    settings = serializers.DictField()
