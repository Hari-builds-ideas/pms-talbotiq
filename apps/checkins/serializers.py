"""Check-in serialisation — plain builders (no email exposed; person = id+display)."""
from __future__ import annotations

from .models import CheckIn


def _person(user) -> dict:
    return {"id": str(user.id), "display": (getattr(user, "display_name", "") or "").strip() or "Someone"}


def serialize_checkin(ci: CheckIn) -> dict:
    resp = getattr(ci, "response", None)
    return {
        "id": str(ci.id),
        "author": _person(ci.author),
        "week_of": ci.week_of.isoformat(),
        "mood": ci.mood,
        "wins": ci.wins,
        "blockers": ci.blockers,
        "learning": ci.learning,
        "priorities": [
            {"id": str(p.id), "text": p.text, "status": p.status} for p in ci.priorities.all()
        ],
        "response": (
            {
                "comment": resp.comment,
                "reaction": resp.reaction,
                "follow_up": resp.follow_up,
                "add_to_one_on_one": resp.add_to_one_on_one,
                "responder": _person(resp.responder),
            }
            if resp is not None
            else None
        ),
        "created_at": ci.created_at.isoformat(),
    }


def serialize_list(items) -> list[dict]:
    return [serialize_checkin(ci) for ci in items]
