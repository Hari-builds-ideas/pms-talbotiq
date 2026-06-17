"""
JD serializers — SHAPE only; behaviour lives in the lifecycle and services.

A JD's status and every state-stamped field (``status``, ``source``,
``current_version``, ``approval_route``, the version's ``is_published`` /
``confidence_score`` / ``citations``) are mutated EXCLUSIVELY by the lifecycle
(``lifecycle.py``) and the services (``services.py``) — so the read serializers
mark everything read-only, the input serializers carry ONLY the authoring
inputs, and there is deliberately NO update serializer (no PATCH path exists;
content is written via ``save_draft`` and the transitions).

``tenant`` and ``created_by`` / ``requested_by`` are NEVER client-supplied: the
lifecycle/services stamp the tenant from the bound request and the author from
the authenticated caller.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.core.display import person_label

from .models import JDRequest, JDTemplate, JDVersion, JobDescription


class JobDescriptionSerializer(serializers.ModelSerializer):
    """Read-only output shape for a :class:`JobDescription`. Every mutation goes
    through ``create_jd`` or a lifecycle transition, never through this
    serializer."""

    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = JobDescription
        fields = [
            "id",
            "title",
            "level",
            "department",
            "status",
            "source",
            "current_version",
            "created_by",
            "created_by_name",
            "approval_route",
            "created_at",
        ]
        read_only_fields = fields

    def get_created_by_name(self, obj) -> str | None:
        return person_label(obj.created_by) if obj.created_by_id else None


class JDVersionSerializer(serializers.ModelSerializer):
    """Read-only output shape for one :class:`JDVersion` (the immutable-once-
    published body + the inputs snapshot it was authored/generated from)."""

    class Meta:
        model = JDVersion
        fields = [
            "id",
            "version_number",
            "body",
            "inputs_snapshot",
            "confidence_score",
            "citations",
            "is_published",
            "created_by",
            "created_at",
        ]
        read_only_fields = fields


class JobDescriptionCreateSerializer(serializers.Serializer):
    """Inputs for ``POST /api/jd/``: the role identity plus an optional initial
    body + generation inputs. ``source``/``status``/author are server-set, so
    they are absent here."""

    title = serializers.CharField()
    level = serializers.CharField()
    department = serializers.CharField(required=False, allow_blank=True, default="")
    body = serializers.JSONField(required=False, default=dict)
    inputs = serializers.JSONField(required=False, default=dict)


class JDDraftSerializer(serializers.Serializer):
    """Body for ``POST /api/jd/<pk>/save-draft``. Both fields are OPTIONAL — the
    view passes each through to ``save_draft`` only when present, so an empty
    body is a no-op edit rather than a clobber-to-null."""

    body = serializers.JSONField(required=False)
    inputs = serializers.JSONField(required=False)


class JDTemplateSerializer(serializers.ModelSerializer):
    """Read-only output shape for a :class:`JDTemplate` (a role-family
    scaffold)."""

    class Meta:
        model = JDTemplate
        fields = ["id", "role_family", "title_pattern", "level", "default_body"]
        read_only_fields = fields


class TemplateInstantiateSerializer(serializers.Serializer):
    """Body for ``POST /api/jd/templates/<pk>/instantiate``. All optional —
    blank/absent fields fall back to the template's own pattern/level/department
    inside ``instantiate_template``."""

    title = serializers.CharField(required=False, allow_blank=True)
    level = serializers.CharField(required=False, allow_blank=True)
    department = serializers.CharField(required=False, allow_blank=True, default="")


class JDRequestSerializer(serializers.ModelSerializer):
    """Read-only output shape for a :class:`JDRequest`. ``requested_by`` is the
    authenticated caller and ``status`` / ``fulfilled_jd`` are stamped by the
    services — all read-only."""

    requested_by_name = serializers.SerializerMethodField()

    class Meta:
        model = JDRequest
        fields = [
            "id",
            "requested_by",
            "requested_by_name",
            "title",
            "level",
            "notes",
            "status",
            "fulfilled_jd",
            "created_at",
        ]
        read_only_fields = fields

    def get_requested_by_name(self, obj) -> str | None:
        return person_label(obj.requested_by) if obj.requested_by_id else None


class JDRequestCreateSerializer(serializers.Serializer):
    """Inputs for ``POST /api/jd/requests``: the role a Manager wants authored.
    The requester + tenant are server-set."""

    title = serializers.CharField()
    level = serializers.CharField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class FulfilRequestSerializer(serializers.Serializer):
    """Body for ``POST /api/jd/requests/<pk>/fulfil``: the JD id that satisfies
    the request. A plain UUID — the view resolves it through the TENANT-SCOPED
    manager so a cross-tenant id 404s (never a 400 that leaks existence)."""

    jd = serializers.UUIDField()
