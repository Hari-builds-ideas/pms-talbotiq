"""
Recognition services — the ONE place recognition is created, read, reacted to and
removed. The security-critical function is :func:`recognition_feed`: it builds the
visibility filter SERVER-SIDE so a card never reaches a viewer its level doesn't
permit. Tenant isolation rides on the ``TenantScopedManager`` (every query below is
tenant-bound; a cross-tenant recipient/card is simply invisible → 404).

Visibility rules (a card is visible to viewer ``u``):
  * the two parties (sender, recipient) ALWAYS see their own card;
  * COMPANY    → everyone in the tenant;
  * MANAGER_ONLY → the recipient's direct manager (+ the two parties);
  * TEAM       → the recipient's or sender's immediate team — i.e. ``u`` manages a
                 party, or shares a manager with a party (a peer);
  * PRIVATE    → nobody but the two parties (not even HR/Admin — private is private).
Role/data-scope does NOT widen this: visibility is a property of the card, by design.
"""
from __future__ import annotations

from django.db.models import Q
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.audit.services import record as audit_record

from .models import COMPANY_VALUES, REACTION_EMOJIS, Recognition, RecognitionReaction


def _feed_q(user) -> Q:
    """The visibility predicate as a single ORM filter (efficient + the one source
    of truth for who-can-see-what). Tenant scoping is applied by the manager."""
    me = user.id
    mgr = user.manager_id  # may be None (top of the tree)
    V = Recognition.Visibility

    q = Q(sender_id=me) | Q(recipient_id=me)  # parties always see their own card
    q |= Q(visibility=V.COMPANY)  # everyone in the (already tenant-scoped) tenant
    q |= Q(visibility=V.MANAGER_ONLY, recipient__manager_id=me)  # recipient's manager
    # TEAM: u manages a party, or shares a manager with a party (a peer).
    team = Q(recipient__manager_id=me) | Q(sender__manager_id=me)
    if mgr is not None:
        team |= Q(recipient__manager_id=mgr) | Q(sender__manager_id=mgr)
    q |= Q(visibility=V.TEAM) & team
    return q


def _can_view(rec: Recognition, user) -> bool:
    """In-Python mirror of :func:`_feed_q` for a single loaded card (used to gate
    reacting — you may only react to a card you can see). ``rec`` must have
    ``sender``/``recipient`` loaded (select_related)."""
    if user.id in (rec.sender_id, rec.recipient_id):
        return True
    V = Recognition.Visibility
    if rec.visibility == V.COMPANY:
        return True  # rec was loaded via the tenant-scoped manager → same tenant
    if rec.visibility == V.PRIVATE:
        return False
    if rec.visibility == V.MANAGER_ONLY:
        return rec.recipient.manager_id == user.id
    # TEAM
    rm, sm, um = rec.recipient.manager_id, rec.sender.manager_id, user.manager_id
    return user.id in (rm, sm) or (um is not None and um in (rm, sm))


def create_recognition(sender, *, recipient_id, value, message, visibility, badge="") -> Recognition:
    """Create a recognition from ``sender`` to ``recipient_id`` (same tenant).
    Validates the value/visibility/message, blocks self-recognition, and audits."""
    from apps.identity.models import User

    if value not in COMPANY_VALUES:
        raise ValidationError({"value": "Choose one of the company values."})
    if visibility not in Recognition.Visibility.values:
        raise ValidationError({"visibility": "Invalid visibility."})
    if not (message or "").strip():
        raise ValidationError({"message": "Add a short message."})
    if len(message.strip()) > 1000:
        # The model declares max_length=1000 but TextField length is not
        # DB-enforced — without this check an oversized card lands in the feed.
        raise ValidationError({"message": "Keep the message under 1000 characters."})

    recipient = User.objects.filter(id=recipient_id, is_active=True).first()  # tenant-scoped
    if recipient is None:
        raise NotFound("That person isn't in your workspace.")
    if recipient.id == sender.id:
        raise ValidationError({"recipient": "You can't recognise yourself."})

    rec = Recognition.objects.create(
        sender=sender,
        recipient=recipient,
        value=value,
        message=message.strip(),
        badge=(badge or "").strip(),
        visibility=visibility,
    )
    audit_record(
        action="recognition.created",
        actor=sender,
        target_type="recognition",
        target_id=rec.id,
        metadata={"recipient": str(recipient.id), "value": value, "visibility": visibility},
    )
    return rec


def recognition_feed(user, *, limit=100):
    """The cards ``user`` is permitted to see, newest first. Visibility enforced
    by :func:`_feed_q`; tenant by the manager. ``select_related``/``prefetch`` so
    serialisation doesn't N+1 over sender/recipient/reactions."""
    return (
        Recognition.objects.filter(_feed_q(user))
        .select_related("sender", "recipient")
        .prefetch_related("reactions")
        .distinct()
        .order_by("-created_at")[:limit]
    )


def toggle_reaction(user, recognition_id, emoji) -> dict:
    """Toggle ``user``'s ``emoji`` reaction on a card they can SEE. Reacting to a
    card outside the viewer's visibility is a 404 (never reveal it exists)."""
    if emoji not in REACTION_EMOJIS:
        raise ValidationError({"emoji": "Unsupported reaction."})
    rec = (
        Recognition.objects.select_related("sender", "recipient")
        .filter(id=recognition_id)
        .first()
    )
    if rec is None or not _can_view(rec, user):
        raise NotFound("Recognition not found.")
    existing = RecognitionReaction.objects.filter(
        recognition=rec, user=user, emoji=emoji
    ).first()
    if existing is not None:
        existing.delete(hard=True)  # a reaction has no history value
        return {"recognition": str(rec.id), "emoji": emoji, "reacted": False}
    RecognitionReaction.objects.create(recognition=rec, user=user, emoji=emoji)
    return {"recognition": str(rec.id), "emoji": emoji, "reacted": True}


def delete_recognition(user, recognition_id) -> None:
    """Soft-delete a card — only its sender may remove it (D32). Audited."""
    rec = Recognition.objects.filter(id=recognition_id).first()
    if rec is None:
        raise NotFound("Recognition not found.")
    if rec.sender_id != user.id:
        raise PermissionDenied("Only the sender can remove a recognition.")
    rec.delete()  # soft
    audit_record(
        action="recognition.deleted",
        actor=user,
        target_type="recognition",
        target_id=rec.id,
    )


def recognition_analytics(user) -> dict:
    """Light, AGGREGATE-only recognition stats for a Manager+ (tenant-scoped):
    total volume, top company values, a visibility breakdown, and the CALLER's own
    given/received counts. Deliberately no per-person leaderboard — that would
    re-identify individuals; aggregate + own-counts only (RW_BUILD_2 2.2)."""
    from django.db.models import Count

    qs = Recognition.objects.all()  # tenant-scoped by the manager
    total = qs.count()
    top_values = [
        {"value": r["value"], "count": r["n"]}
        for r in qs.values("value").annotate(n=Count("id")).order_by("-n", "value")[:5]
    ]
    by_visibility = {
        r["visibility"]: r["n"] for r in qs.values("visibility").annotate(n=Count("id"))
    }
    return {
        "total": total,
        "top_values": top_values,
        "by_visibility": by_visibility,
        "you": {
            "given": qs.filter(sender_id=user.id).count(),
            "received": qs.filter(recipient_id=user.id).count(),
        },
    }


def reactions_summary(rec: Recognition, user) -> dict:
    """``{counts: {emoji: n}, mine: [emoji,...]}`` from the prefetched reactions."""
    counts: dict[str, int] = {}
    mine: set[str] = set()
    for rx in rec.reactions.all():
        counts[rx.emoji] = counts.get(rx.emoji, 0) + 1
        if rx.user_id == user.id:
            mine.add(rx.emoji)
    return {"counts": counts, "mine": sorted(mine)}
