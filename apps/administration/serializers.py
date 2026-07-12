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
    """Read-only projection of a user for the Admin Hub user list / responses.
    ``display`` is the effective name (``display_name`` or email fallback)."""

    display = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "display_name", "display", "role", "manager",
                  "is_active", "mfa_enabled"]
        read_only_fields = fields


class TenantConfigSerializer(serializers.ModelSerializer):
    """Read-only projection of the tenant's config row."""

    class Meta:
        model = TenantConfig
        fields = ["id", "settings", "version"]
        read_only_fields = fields


# ── input ────────────────────────────────────────────────────────────────────


class CreateUserSerializer(serializers.Serializer):
    """Body for ``POST /users``. ``manager`` is an optional UUID resolved in the
    view to a tenant-scoped ``User`` (cross-tenant id → 404). ``display_name`` is
    optional (falls back to email when absent)."""

    email = serializers.EmailField()
    role = serializers.CharField()
    manager = serializers.UUIDField(required=False, allow_null=True, default=None)
    password = serializers.CharField(required=False, allow_null=True, default=None)
    display_name = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, default=None
    )


class SetRoleSerializer(serializers.Serializer):
    """Body for ``POST /users/<id>/role``."""

    role = serializers.CharField()


class DisplayNameSerializer(serializers.Serializer):
    """Body for ``POST /users/<id>/display-name``. Blank/null clears it (→ email
    fallback)."""

    display_name = serializers.CharField(allow_null=True, allow_blank=True)


class OrgProfileFieldsSerializer(serializers.Serializer):
    """Body for ``PATCH /users/<id>/profile`` (PHASE2 L1.1) — the ORG-controlled
    profile fields an Admin sets (a person doesn't set their own job title)."""

    title = serializers.CharField(max_length=128, required=False, allow_blank=True)
    department = serializers.CharField(max_length=128, required=False, allow_blank=True)
    employee_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)


class ReportingLineSerializer(serializers.Serializer):
    """Body for ``POST /users/<id>/reporting-line``. ``manager`` is the new
    manager's UUID, resolved in the view to a tenant-scoped ``User``."""

    manager = serializers.UUIDField()


class TenantConfigUpdateSerializer(serializers.Serializer):
    """Body for ``PUT /tenant-config``: the full ``settings`` bag (a JSON object)."""

    settings = serializers.DictField()
