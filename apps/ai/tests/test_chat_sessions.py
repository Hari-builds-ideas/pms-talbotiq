"""
Chat session memory (OVERNIGHT_A1/A5) — short-term, per-user, scope-safe. The proofs:
  * a session persists across requests and resumes within the TTL;
  * a session is OWNER-bound — another user can't list or read it (404, no leak);
  * an expired session returns empty history and resolves no references;
  * a cross-turn reference resolves to the RIGHT object ONLY if the caller can still
    see it; a not-visible reference resolves to nothing (the caller says "I don't see
    a recent … in this conversation", never why).
All planner/chat outputs use the deterministic FakeLLMProvider — no live calls.
"""
from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.ai import sessions
from apps.ai.models import CHAT_SESSION_TTL_HOURS, ChatSession, ChatTurn
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import ReviewFactory, CycleFactory

pytestmark = pytest.mark.django_db
FAKE = {"LLM_PROVIDER": "apps.ai.providers.FakeLLMProvider"}
PLAN = "/api/ai/chat/plan"
SESSIONS = "/api/ai/chat/sessions"


def _client(user):
    access, _ = issue_tokens_for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return c


def _name(user, name):
    user.display_name = name
    user.save(update_fields=["display_name"])


@override_settings(**FAKE)
def test_session_persists_and_resumes_across_requests(org):
    with tenant_context(org.tenant):
        _name(org.report, "Rhea Report")
    c = _client(org.manager)
    r1 = c.post(PLAN, {"query": "start a 360 for Rhea"}, format="json")
    assert r1.status_code == 200, r1.content
    sid = r1.json()["session_id"]
    # Second request with the same session_id resumes it (no new session).
    r2 = c.post(PLAN, {"query": "how am I doing?", "session_id": sid}, format="json")
    assert r2.json()["session_id"] == sid
    detail = c.get(f"{SESSIONS}/{sid}")
    assert detail.status_code == 200
    # Both user turns are in history (persisted across requests).
    texts = [t["text"] for t in detail.json()["turns"] if t["role"] == "user"]
    assert "start a 360 for Rhea" in texts and "how am I doing?" in texts


@override_settings(**FAKE)
def test_sessions_are_owner_isolated(org):
    c = _client(org.manager)
    sid = c.post(PLAN, {"query": "start a 360 for someone"}, format="json").json()["session_id"]
    # The manager sees the session in their list…
    assert any(s["id"] == sid for s in _client(org.manager).get(SESSIONS).json())
    # …another user does NOT, and can't read it (404, not 403 — no existence leak).
    other = _client(org.report)
    assert all(s["id"] != sid for s in other.get(SESSIONS).json())
    assert other.get(f"{SESSIONS}/{sid}").status_code == 404


@override_settings(**FAKE)
def test_cross_tenant_session_is_invisible(org, other_tenant):
    from apps.testsupport.factories import UserFactory

    outsider = UserFactory(tenant=other_tenant, role="ADMIN", email="boss@other.test")
    sid = _client(org.manager).post(PLAN, {"query": "start a 360 for someone"}, format="json").json()["session_id"]
    # A user in another tenant can't read it — the scoped manager makes it a 404.
    assert _client(outsider).get(f"{SESSIONS}/{sid}").status_code == 404


@override_settings(**FAKE)
def test_expired_session_returns_empty_history_and_404_on_fetch(org):
    c = _client(org.manager)
    sid = c.post(PLAN, {"query": "start a 360 for someone"}, format="json").json()["session_id"]
    # Backdate the activity past the TTL (update() bypasses auto_now). Must run inside
    # a bound tenant — the scoped manager fails closed otherwise (update 0 rows).
    old = timezone.now() - timedelta(hours=CHAT_SESSION_TTL_HOURS + 1)
    with tenant_context(org.tenant):
        ChatSession.objects.filter(id=sid).update(last_activity=old)
        s = ChatSession.objects.get(id=sid)
        assert s.is_expired is True
        assert sessions.recent_turns(s) == []
        assert sessions.fetch_session_or_none(org.manager, sid) is None
    assert c.get(f"{SESSIONS}/{sid}").status_code == 404


@override_settings(**FAKE)
def test_cross_turn_person_reference_resolves_in_scope(org):
    """A prior turn referenced Rhea (a report); a later "her" resolves to her."""
    with tenant_context(org.tenant):
        _name(org.report, "Rhea Report")
        session = ChatSession.objects.create(tenant_id=org.tenant.id, owner=org.manager)
        sessions.append_turn(session, ChatTurn.Role.USER, "start a 360 for Rhea")
        sessions.append_turn(
            session, ChatTurn.Role.ASSISTANT, "Planned a 360 for Rhea.",
            refs=[{"type": "user", "id": str(org.report.id), "label": "Rhea Report"}],
        )
        person = sessions.resolve_person_reference(org.manager, session, "now draft her review")
        assert person is not None and person.id == org.report.id


@override_settings(**FAKE)
def test_people_in_order_persists_beyond_recent_window(org):
    """"the first person we discussed" must still resolve in a LONG thread: entity
    references persist beyond the ~20-turn verbatim window (§1). Ground person A in
    turn 1, bury it under 25 filler turns, ground person B late — A is still first."""
    from apps.testsupport.factories import UserFactory

    with tenant_context(org.tenant):
        _name(org.report, "Alpha First")
        second = UserFactory(tenant=org.tenant, role="EMPLOYEE", manager=org.manager,
                             email="bravo@acme.test", display_name="Bravo Second")
        s = ChatSession.objects.create(tenant_id=org.tenant.id, owner=org.manager)
        sessions.append_turn(
            s, ChatTurn.Role.ASSISTANT, "About Alpha First.",
            refs=[{"type": "user", "id": str(org.report.id), "label": "Alpha First"}])
        for i in range(25):  # push turn 1 out of the recent verbatim window
            sessions.append_turn(s, ChatTurn.Role.USER, f"filler {i}")
        sessions.append_turn(
            s, ChatTurn.Role.ASSISTANT, "About Bravo Second.",
            refs=[{"type": "user", "id": str(second.id), "label": "Bravo Second"}])
        order = sessions.people_in_order(org.manager, s)
    names = [u.display for u in order]
    # Alpha (turn 1) is still FIRST despite rolling off the recent window; Bravo second.
    assert names[:2] == ["Alpha First", "Bravo Second"]


@override_settings(**FAKE)
def test_reference_to_not_visible_person_resolves_to_nothing(org):
    """A stored ref never widens access: a peer (out of the manager's scope) can't be
    resolved even if a turn recorded them — resolution returns None (never why)."""
    with tenant_context(org.tenant):
        session = ChatSession.objects.create(tenant_id=org.tenant.id, owner=org.manager)
        sessions.append_turn(
            session, ChatTurn.Role.ASSISTANT, "…",
            refs=[{"type": "user", "id": str(org.peer.id), "label": "Peer"}],  # peer reports to HRBP
        )
        assert sessions.resolve_person_reference(org.manager, session, "draft her review") is None


@override_settings(**FAKE)
def test_review_reference_resolves_only_if_in_scope(org):
    with tenant_context(org.tenant):
        in_scope = ReviewFactory(
            employee=org.report, cycle=CycleFactory(tenant=org.tenant, status="ACTIVE"), state="DRAFT"
        )
        out_scope = ReviewFactory(
            employee=org.peer, cycle=CycleFactory(tenant=org.tenant, status="ACTIVE"), state="DRAFT"
        )
        session = ChatSession.objects.create(tenant_id=org.tenant.id, owner=org.manager)
        sessions.append_turn(
            session, ChatTurn.Role.ASSISTANT, "drafts",
            refs=[
                {"type": "review", "id": str(out_scope.id), "label": "Peer"},
                {"type": "review", "id": str(in_scope.id), "label": "Rhea"},
            ],
        )
        kind, obj = sessions.resolve_reference(org.manager, session, "open the review we just drafted")
        assert kind == "review" and obj.id == in_scope.id  # the in-scope one, never the peer's
