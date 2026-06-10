"""
Org-chart serializers — SHAPE only; behaviour lives in the services
(``services.py``), the position writes (``positions.py``) and the reassignment
(``reassign.py``).

A :class:`Position`'s ``status`` and every state-stamped field (``status``,
``filled_by``, ``opened_at``, ``filled_at``, ``published_jd``) are mutated
EXCLUSIVELY by the position writes — so the read serializer marks everything
read-only and the input serializers carry ONLY the client-supplied inputs, with
deliberately NO update serializer (no PATCH path exists; state changes go through
fill / close / link-jd / unlink-jd).

``tenant`` and ``created_by`` are NEVER client-supplied: the position writes
stamp the tenant from the actor's bound request and the creator from the
authenticated caller. The referenced users / JDs are carried as bare UUIDs and
resolved by the view through their TENANT-SCOPED managers so a cross-tenant id
404s (never a 400 that leaks existence).

The tree / person-card / search / export / vacancy endpoints return plain
dicts/lists straight from the services — there is no serializer for them.
"""
from __future__ import annotations

from rest_framework import serializers

from .models import Position


class PositionSerializer(serializers.ModelSerializer):
    """Read-only output shape for a :class:`Position`. Every mutation goes
    through a ``positions`` write (create / fill / close / link-jd / unlink-jd),
    never through this serializer."""

    class Meta:
        model = Position
        fields = [
            "id",
            "title",
            "department",
            "status",
            "reports_to",
            "filled_by",
            "published_jd",
            "opened_at",
            "filled_at",
            "created_at",
        ]
        read_only_fields = fields


class PositionCreateSerializer(serializers.Serializer):
    """Inputs for ``POST /api/org/positions``: the role title, the manager it
    reports to, and an optional department + PUBLISHED JD link. ``status`` /
    ``created_by`` / tenant are server-set, so they are absent here. The
    ``reports_to`` / ``published_jd`` UUIDs are resolved by the view through the
    tenant-scoped managers (cross-tenant id → 404)."""

    title = serializers.CharField()
    reports_to = serializers.UUIDField()
    department = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default=None
    )
    published_jd = serializers.UUIDField(required=False, allow_null=True, default=None)


class PositionFillSerializer(serializers.Serializer):
    """Body for ``POST /api/org/positions/<pk>/fill``: the employee id that fills
    the seat. A plain UUID — the view resolves it through the tenant-scoped
    manager so a cross-tenant id 404s."""

    filled_by = serializers.UUIDField()


class PositionLinkJDSerializer(serializers.Serializer):
    """Body for ``POST /api/org/positions/<pk>/link-jd``: the PUBLISHED JD id to
    link. A plain UUID — the view resolves it through the tenant-scoped manager
    (cross-tenant id → 404); the write 422s if the JD is not PUBLISHED."""

    jd = serializers.UUIDField()


class ReassignSerializer(serializers.Serializer):
    """Body for ``POST /api/org/reassign``: move ``user`` to report to
    ``new_manager``. Both are bare UUIDs resolved by the view through the
    tenant-scoped manager (cross-tenant id → 404); the write 422s on a cycle or
    an inactive / cross-tenant manager."""

    user = serializers.UUIDField()
    new_manager = serializers.UUIDField()
