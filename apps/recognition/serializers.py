"""
Recognition serialisation — plain builders (the reaction summary needs the viewing
user, so a function is clearer than DRF serializer context). Person display reuses
``display_name`` like the rest of the app; no email is exposed in the feed.
"""
from __future__ import annotations

from .models import Recognition
from .services import reactions_summary


def _person(user) -> dict:
    return {
        "id": str(user.id),
        "display": (getattr(user, "display_name", "") or "").strip() or "Someone",
    }


def serialize_recognition(rec: Recognition, viewer) -> dict:
    """One card as the feed returns it — sender/recipient display, the value,
    message, badge, visibility, reactions (counts + which the viewer added), and
    whether the viewer may remove it (sender only)."""
    return {
        "id": str(rec.id),
        "sender": _person(rec.sender),
        "recipient": _person(rec.recipient),
        "value": rec.value,
        "message": rec.message,
        "badge": rec.badge,
        "visibility": rec.visibility,
        "created_at": rec.created_at.isoformat(),
        "reactions": reactions_summary(rec, viewer),
        "can_delete": rec.sender_id == viewer.id,
    }


def serialize_feed(recs, viewer) -> list[dict]:
    return [serialize_recognition(r, viewer) for r in recs]
