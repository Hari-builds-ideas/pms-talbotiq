"""
Feedback serializers — SHAPE only; behaviour lives in ``services.py``.

THE EGRESS-STRIPPING RULE LIVES HERE (defence in depth on top of RBAC): the
giver identity NEVER leaves the API except to the giver viewing their OWN
feedback. Concretely:

* :class:`OwnFeedbackSerializer` (the only serializer that renders a Feedback
  row) carries NO ``giver`` field at all — it is only ever used for the
  authenticated caller's own items, so the giver IS the caller.
* :class:`ReceivedContinuousFeedbackSerializer` (what a recipient sees of
  continuous feedback) likewise has NO ``giver`` field.
* A recipient's 360 view is NEVER a serialized Feedback row — the view returns
  :func:`apps.feedback.anonymize.build_anonymized_payload` verbatim (already
  stripped + pseudonymised + volume-gated). There is deliberately no
  "AnonymousFeedbackSerializer" model serializer.
* :class:`FeedbackRequestSerializer` shows ``giver`` ONLY on the two endpoints
  where the caller already knows it: the inviting manager's per-cycle request
  list (they sent the invitations) and the giver's own ``/requests/mine``.
  Invitations are never joined to submitted content via the API, so this leaks
  WHO WAS ASKED, to the asker — never who said what.
* :class:`FeedbackSummarySerializer` omits ``reviewed_by`` entirely — the
  HRBP reviewer identity is not the subject's business.

ANTI-SPOOF: no input serializer accepts ``giver`` / ``opened_by`` /
``reviewed_by`` — those are always ``request.user`` (the services enforce it
again). ``tenant`` is never accepted or echoed.
"""
from __future__ import annotations

from rest_framework import serializers

from .models import (
    Feedback,
    FeedbackCycle,
    FeedbackRequest,
    FeedbackSummary,
    OneOnOneNote,
)

# ── cycles ──────────────────────────────────────────────────────────────────


class FeedbackCycleSerializer(serializers.ModelSerializer):
    """Read-only output shape for a :class:`FeedbackCycle`. The subject's
    identity is not secret (recipients know whose 360 this is); givers never
    appear here. ``opened_by`` is deliberately omitted — no identity egress
    beyond the subject."""

    class Meta:
        model = FeedbackCycle
        fields = [
            "id",
            "subject",
            "status",
            "opened_at",
            "closed_at",
            "min_volume",
            "performance_cycle",
        ]
        read_only_fields = fields


class FeedbackCycleCreateSerializer(serializers.Serializer):
    """Inputs for ``POST /api/feedback/cycles``. Plain UUIDs — the view
    resolves them through the TENANT-SCOPED managers so a cross-tenant id 404s
    (never a 400 that leaks existence). ``opened_by`` is server-set."""

    subject = serializers.UUIDField()
    performance_cycle = serializers.UUIDField(required=False, allow_null=True)
    min_volume = serializers.IntegerField(required=False, allow_null=True, min_value=1)


# ── invitations ─────────────────────────────────────────────────────────────


class FeedbackRequestSerializer(serializers.ModelSerializer):
    """Invitation row WITH the giver — only for the inviter's per-cycle list
    (MANAGE_FEEDBACK_CYCLE in scope) and the giver's own ``/requests/mine``.
    See the module docstring for why this is not an identity leak."""

    class Meta:
        model = FeedbackRequest
        fields = ["id", "cycle", "giver", "relationship", "status"]
        read_only_fields = fields


class FeedbackRequestCreateSerializer(serializers.Serializer):
    """Inputs for inviting a giver onto a cycle. The relationship is fixed by
    the inviter HERE, never client-supplied at submit time."""

    giver = serializers.UUIDField()
    relationship = serializers.ChoiceField(choices=FeedbackRequest.Relationship.choices)


# ── feedback items (giver-facing only) ──────────────────────────────────────


class OwnFeedbackSerializer(serializers.ModelSerializer):
    """A giver's view of their OWN feedback item. NO ``giver`` field — the
    giver is the authenticated caller by construction; this serializer must
    never be handed anyone else's rows."""

    class Meta:
        model = Feedback
        fields = [
            "id",
            "cycle",
            "subject",
            "relationship",
            "kind",
            "body",
            "giver_marked_sensitive",
            "created_at",
        ]
        read_only_fields = fields


class ReceivedContinuousFeedbackSerializer(serializers.ModelSerializer):
    """A recipient's view of CONTINUOUS feedback about them: the words, never
    the author. NO ``giver``, no subject echo needed (it is the caller)."""

    class Meta:
        model = Feedback
        fields = ["id", "relationship", "kind", "body", "created_at"]
        read_only_fields = fields


class GiveFeedbackSerializer(serializers.Serializer):
    """Inputs for submitting 360 feedback. The giver is ALWAYS request.user and
    the relationship comes FROM the invitation — neither is accepted here."""

    body = serializers.CharField()
    marked_sensitive = serializers.BooleanField(required=False, default=False)


class ContinuousFeedbackSerializer(serializers.Serializer):
    """Inputs for cycle-less continuous feedback. Giver is request.user."""

    subject = serializers.UUIDField()
    body = serializers.CharField()
    marked_sensitive = serializers.BooleanField(required=False, default=False)


class EditFeedbackSerializer(serializers.Serializer):
    """PATCH inputs for editing one's own feedback (service enforces giver +
    immutability after close)."""

    body = serializers.CharField(required=False)
    marked_sensitive = serializers.BooleanField(required=False)


# ── summaries ───────────────────────────────────────────────────────────────


class FeedbackSummarySerializer(serializers.ModelSerializer):
    """Read-only summary shape, shared by the HRBP review queue and the
    subject's released view. ``reviewed_by`` is deliberately ABSENT (no
    reviewer-identity egress to the subject); givers never appear in a summary
    by construction (it is built from the anonymised payload)."""

    class Meta:
        model = FeedbackSummary
        fields = [
            "id",
            "cycle",
            "subject",
            "sections",
            "status",
            "anonymity_passed",
            "sensitive",
            "volume_total",
            "insufficient_groups",
            "insufficient_volume",
            "confidence_score",
            "generated_at",
            "released_at",
        ]
        read_only_fields = fields


# ── 1:1 notes ───────────────────────────────────────────────────────────────


class OneOnOneNoteSerializer(serializers.ModelSerializer):
    """Read shape for a 1:1 note. Both participants are named — a 1:1 is
    mutual, attributed working context (never anonymised) and is only ever
    serialized TO a participant."""

    class Meta:
        model = OneOnOneNote
        fields = ["id", "manager", "employee", "body", "meeting_date", "created_at"]
        read_only_fields = fields


class OneOnOneNoteCreateSerializer(serializers.Serializer):
    """Inputs for creating a 1:1 note. The view enforces that request.user IS
    one of the two named participants (403 otherwise)."""

    manager = serializers.UUIDField()
    employee = serializers.UUIDField()
    body = serializers.CharField()
    meeting_date = serializers.DateField()


class OneOnOneNoteEditSerializer(serializers.Serializer):
    """PATCH inputs for a 1:1 note (participants only, enforced in the view)."""

    body = serializers.CharField(required=False)
    meeting_date = serializers.DateField(required=False)
