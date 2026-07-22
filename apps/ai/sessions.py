"""
Chat session memory (OVERNIGHT_A1 + A5) — short-term, per-user, scope-safe.

A :class:`~apps.ai.models.ChatSession` holds the recent turns of one user's
conversation so the agent can (a) resume when the panel is reopened within the
TTL and (b) resolve cross-turn references ("the review we just drafted", "her").

THE SAFETY RULES (never weakened):
  * a session is bound to its ``owner`` — another user can never read it (a
    cross-user id is filtered out → 404/403) and the tenant-scoped manager makes a
    cross-tenant id invisible;
  * a reference NEVER widens access: every resolved object is RE-CHECKED against
    the caller's live scope (``actor_can_access`` / the scoped getters). An object
    the caller can no longer see resolves to ``None`` — and the caller-facing text
    says only "I don't see a recent … in this conversation", never *why*;
  * an expired session (idle past the TTL) returns empty history and resolves
    nothing — short-term memory only, by design.

Turn ``refs`` are DATA: ``[{"type": "review"|"user"|…, "id": "<uuid>",
"label": "<display>"}]``. They are never re-interpreted as commands.
"""
from __future__ import annotations

import re
import uuid

from apps.ai.models import ChatPlan, ChatSession, ChatTurn
from apps.rbac.scope import actor_can_access

#: Recent turns kept for memory / reference resolution.
RECENT_TURNS = 20

#: Cue words → the ref TYPE a deictic phrase is asking about. Checked longest-first.
_TYPE_CUES = {
    "review": "review",
    "roadmap": "roadmap",
    "career": "roadmap",
    "recognition": "recognition",
    "kudos": "recognition",
    "360": "feedback_cycle",
    "feedback cycle": "feedback_cycle",
    "cycle": "feedback_cycle",
    "succession": "succession_plan",
    "plan": "succession_plan",
}

#: Pronoun / deixis that means "the person we were just talking about".
_PERSON_DEIXIS = re.compile(r"\b(they|them|their|her|him|his|she|he|that person|the same person|this person)\b", re.I)


def _valid_uuid(value) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def get_session(user, session_id=None) -> ChatSession:
    """Return the caller's live session for ``session_id`` (owner-scoped, not
    expired), else a NEW session. Never returns another user's session — an
    unknown / unowned / cross-tenant / expired id silently starts a fresh one, so
    a probe can't confirm a session exists."""
    if session_id and _valid_uuid(session_id):
        existing = ChatSession.objects.filter(id=session_id, owner=user).first()
        if existing is not None and not existing.is_expired:
            return existing
    return ChatSession.objects.create(tenant_id=user.tenant_id, owner=user)


def fetch_session_or_none(user, session_id) -> ChatSession | None:
    """Strict fetch for the GET endpoints: the caller's own, non-expired session or
    ``None`` (the view maps to 404). Never leaks another user's/tenant's session."""
    if not _valid_uuid(session_id):
        return None
    s = ChatSession.objects.filter(id=session_id, owner=user).first()
    if s is None or s.is_expired:
        return None
    return s


def append_turn(session: ChatSession, role: str, text: str, *, refs=None, plan: ChatPlan | None = None) -> ChatTurn:
    """Append a turn and bump the session's activity (resets the TTL). ``refs`` are
    the in-scope objects this turn was grounded in (data only)."""
    turn = ChatTurn.objects.create(
        tenant_id=session.tenant_id,
        session=session,
        role=role,
        text=(text or "")[:8000],
        refs=refs or [],
        plan=plan,
    )
    if not session.title and role == ChatTurn.Role.USER and text:
        session.title = text.strip()[:120]
    session.save(update_fields=["title", "last_activity"])  # auto_now bumps last_activity
    return turn


def recent_turns(session: ChatSession, limit: int = RECENT_TURNS) -> list[ChatTurn]:
    """The session's most recent turns, oldest→newest, or ``[]`` if expired."""
    if session.is_expired:
        return []
    turns = list(session.turns.order_by("-created_at")[:limit])
    turns.reverse()
    return turns


def _all_refs_newest_first(session: ChatSession) -> list[dict]:
    """Every ref across the session's recent turns, newest turn first (and within a
    turn, later refs first). ``[]`` when expired."""
    out: list[dict] = []
    for turn in reversed(recent_turns(session)):  # newest first
        for ref in reversed(turn.refs or []):
            if isinstance(ref, dict) and ref.get("id"):
                out.append(ref)
    return out


def _reaccess(user, ref: dict):
    """Re-check the caller can STILL see ``ref``'s object and return it, else None.
    This is the load-bearing gate: a stored ref never grants access on its own."""
    rtype, rid = ref.get("type"), ref.get("id")
    if not _valid_uuid(rid):
        return None
    if rtype == "user":
        from apps.identity.models import User

        subject = User.objects.filter(id=rid).first()  # tenant-scoped
        return subject if (subject and actor_can_access(user, subject)) else None
    if rtype == "review":
        from apps.reviews.models import Review

        review = Review.objects.filter(id=rid).select_related("employee").first()
        return review if (review and actor_can_access(user, review.employee)) else None
    if rtype == "roadmap":
        from apps.career import services as career_services

        try:
            return career_services.get_roadmap_in_scope(user, rid)
        except Exception:  # noqa: BLE001 — out-of-scope 404 → not resolvable
            return None
    if rtype == "recognition":
        from apps.recognition.models import Recognition
        from apps.recognition.services import _can_view

        rec = Recognition.objects.filter(id=rid).select_related("sender", "recipient").first()
        return rec if (rec and _can_view(rec, user)) else None
    return None


def _wanted_type(text: str) -> str | None:
    m = (text or "").lower()
    for cue in sorted(_TYPE_CUES, key=len, reverse=True):
        if cue in m:
            return _TYPE_CUES[cue]
    return None


def resolve_reference(user, session: ChatSession, text: str):
    """Resolve a deictic reference in ``text`` ("the review we just drafted", "her")
    to a real object from the session's recent refs — RE-CHECKING access every time.

    Returns ``(kind, obj)`` where ``kind`` is the ref type and ``obj`` the live,
    in-scope object, or ``(None, None)`` when nothing resolves (the caller then
    shows the safe "I don't see a recent … in this conversation" line — never why).
    """
    if session.is_expired:
        return None, None
    refs = _all_refs_newest_first(session)
    if not refs:
        return None, None
    wanted = _wanted_type(text)
    is_person_deixis = bool(_PERSON_DEIXIS.search(text or ""))
    for ref in refs:
        rtype = ref.get("type")
        # Match by explicit type cue, OR person-deixis → the most recent user ref.
        if wanted is not None and rtype != wanted:
            continue
        if wanted is None and is_person_deixis and rtype != "user":
            continue
        if wanted is None and not is_person_deixis:
            continue
        obj = _reaccess(user, ref)
        if obj is not None:
            return rtype, obj
    return None, None


def resolve_person_reference(user, session: ChatSession, text: str):
    """Convenience for the planner: the most recent in-scope PERSON a deictic phrase
    ("her", "that person") refers to, or ``None``. Access re-checked."""
    if not _PERSON_DEIXIS.search(text or ""):
        return None
    for ref in _all_refs_newest_first(session):
        if ref.get("type") == "user":
            obj = _reaccess(user, ref)
            if obj is not None:
                return obj


def last_offered_people(user, session: ChatSession):
    """The ORDERED people offered in the most recent disambiguation ("several match:
    A, B") — so a follow-up "the first/second/other one" can pick from them. Access
    re-checked on each (a stored ref grants nothing). Empty when there was none."""
    if session.is_expired:
        return []
    from apps.identity.models import User

    for turn in reversed(recent_turns(session)):  # newest turn first
        urefs = [
            r for r in (turn.refs or [])
            if isinstance(r, dict) and r.get("type") == "user" and _valid_uuid(r.get("id"))
        ]
        if len(urefs) >= 2:  # a disambiguation grounds ≥2 people, in offered order
            out = []
            for r in urefs:
                u = User.objects.filter(id=r["id"]).first()
                if u is not None and actor_can_access(user, u):
                    out.append(u)
            return out
    return []


def last_referenced_person_any_scope(user, session: ChatSession):
    """The most recent PERSON the caller referred to this session, WITHOUT the
    access gate — so a pronoun follow-up can be told "you still can't see X"
    instead of silently switching to the caller. Tenant-scoped only (the scoped
    manager still isolates tenants); the CALLER re-checks scope before showing any
    data. Returns a ``User`` or ``None``."""
    if session.is_expired:
        return None
    from apps.identity.models import User

    for ref in _all_refs_newest_first(session):
        if ref.get("type") == "user" and _valid_uuid(ref.get("id")):
            u = User.objects.filter(id=ref["id"]).first()  # tenant-scoped
            if u is not None:
                return u
    return None
    return None
