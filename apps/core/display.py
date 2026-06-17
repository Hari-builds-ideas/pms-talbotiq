"""
Human-label resolution for entity FKs exposed in API payloads.

The headline UI rule: **a raw UUID must never be shown to a human.** Serializers
that expose a person/entity FK as a bare id also expose a resolved label next to
it (``reviewer`` + ``reviewer_name``, ``cycle`` + ``cycle_name`` …). Resolving on
the server (not via a scope-limited client directory) means the label is correct
even for an actor outside the caller's org-tree scope or for a non-user entity.

``person_label`` is the single source of that label: the user's ``display_name``
when set, else the email local-part — never the email domain, never a uuid. It
returns ``None`` for a null FK so the caller can render a placeholder. It does NOT
make any authorization decision: anonymity/scope is the serializer's job (a 360
giver is never passed here; a recipient never sees a resolved giver).
"""
from __future__ import annotations


def person_label(user) -> str | None:
    """A human label for a user object: ``display_name``, else the email
    local-part. Never a raw uuid; ``None`` for a null user."""
    if user is None:
        return None
    name = getattr(user, "display_name", None)
    if name:
        return name
    email = getattr(user, "email", None) or ""
    local = email.split("@")[0]
    return local or None
