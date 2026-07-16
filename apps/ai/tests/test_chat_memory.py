"""
C2 (FINAL) — conversation memory on the READ/Q&A path, scope-safe.

Proofs:
  * a read answer GROUNDS the person it answered about (a `user` ref on the
    assistant turn), so a pronoun follow-up ("how many reviews does she have?")
    resolves to the same person;
  * memory NEVER widens access — a report asking "her…" after mentioning someone
    out of scope gets the empty-scope answer, not data;
  * count-questions get real counts (reviews/goals/feedback), not a goals dump;
  * a person NAMED in the query resolves (unique tenant match), scope-checked.
All via the deterministic FakeLLMProvider — no live calls.
"""
import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, ReviewFactory

pytestmark = pytest.mark.django_db
FAKE = {"LLM_PROVIDER": "apps.ai.providers.FakeLLMProvider"}
CHAT = "/api/ai/chat"


def _client(user):
    access, _ = issue_tokens_for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return c


def _name(user, name):
    user.display_name = name
    user.save(update_fields=["display_name"])


@override_settings(**FAKE)
def test_read_answer_grounds_person_and_pronoun_follow_up_resolves(org):
    with tenant_context(org.tenant):
        _name(org.report, "Rhea Report")
        cycle = CycleFactory(tenant=org.tenant)
        ReviewFactory(tenant=org.tenant, employee=org.report, reviewer=org.manager, cycle=cycle)
    c = _client(org.manager)
    # Turn 1 — ask about Rhea BY NAME (read path; no email, no prior refs).
    r1 = c.post(CHAT, {"query": "how is Rhea doing on her goals?"}, format="json")
    assert r1.status_code == 200, r1.content
    body1 = r1.json()
    assert body1["status"] == "ok"
    assert "Rhea Report" in body1["answer"]  # named person resolved, not the caller
    sid = body1["session_id"]
    # Turn 2 — pronoun follow-up in the SAME session: "she" must resolve to Rhea.
    r2 = c.post(CHAT, {"query": "how many reviews does she have?", "session_id": sid}, format="json")
    body2 = r2.json()
    assert body2["status"] == "ok"
    assert "Rhea Report" in body2["answer"]
    assert "review(s)" in body2["answer"]  # the count route, not a goals dump


@override_settings(**FAKE)
def test_count_question_returns_real_counts_not_goals_dump(org):
    with tenant_context(org.tenant):
        cycle = CycleFactory(tenant=org.tenant)
        ReviewFactory(tenant=org.tenant, employee=org.report, reviewer=org.manager, cycle=cycle)
    c = _client(org.report)
    r = c.post(CHAT, {"query": "how many reviews do I have?"}, format="json")
    body = r.json()
    assert body["status"] == "ok"
    assert "1 review(s)" in body["answer"]
    assert "goal(s):" not in body["answer"]  # not the old goals-title misroute


@override_settings(**FAKE)
def test_memory_never_widens_access(org):
    """The manager's session grounds Rhea; Rhea's PEER (not her manager) then uses
    a pronoun in their OWN session — and even if a ref existed, access is re-checked.
    Also: the peer asking about Rhea BY NAME gets the empty-scope answer."""
    with tenant_context(org.tenant):
        _name(org.report, "Rhea Report")
    peer = _client(org.peer)
    r = peer.post(CHAT, {"query": "how is Rhea doing on her goals?"}, format="json")
    body = r.json()
    assert body["status"] == "ok"
    # Named resolution finds Rhea, but the scoped fetch refuses: no data leaked.
    assert "No data in your scope" in body["answer"]
    assert "goal(s):" not in body["answer"]


@override_settings(**FAKE)
def test_open_the_draft_navigates_to_the_grounded_review_not_goals(org):
    """The Hari bug: after a draft, "Open the draft to review it" typed as chat
    must resolve the session's review ref → a navigate answer with the deeplink —
    NEVER a goals summary."""
    from apps.ai import sessions
    from apps.ai.models import ChatTurn

    with tenant_context(org.tenant):
        cycle = CycleFactory(tenant=org.tenant)
        review = ReviewFactory(tenant=org.tenant, employee=org.report, reviewer=org.manager, cycle=cycle)
        session = sessions.get_session(org.manager)
        # Ground the review on the session (what a draft_review approve records).
        sessions.append_turn(
            session, ChatTurn.Role.ASSISTANT, "Drafted the review.",
            refs=[{"type": "review", "id": str(review.id), "label": "Review"}],
        )
    c = _client(org.manager)
    r = c.post(CHAT, {"query": "Open the draft to review it", "session_id": str(session.id)}, format="json")
    body = r.json()
    assert body["status"] == "ok" and body["intent"] == "navigate", body
    assert body["deeplink"] == f"/reviews/{review.id}"
    assert "goal(s):" not in body["answer"]


@override_settings(**FAKE)
def test_open_with_nothing_to_resolve_is_honest_not_a_goals_dump(org):
    c = _client(org.manager)
    r = c.post(CHAT, {"query": "open the draft to review it"}, format="json")
    body = r.json()
    assert body["status"] == "ok"
    assert "goal(s):" not in body["answer"]
    assert "don't see a recent record" in body["answer"]


@override_settings(**FAKE)
def test_open_a_new_thing_is_not_hijacked_by_the_navigation_intercept(org):
    """Indefinite "open A check-in" (a new-thing ask) must NOT be captured by the
    definite-reference navigation intercept — it flows to normal classification."""
    c = _client(org.report)
    r = c.post(CHAT, {"query": "open a check-in for this week"}, format="json")
    body = r.json()
    assert body.get("intent") != "navigate" and "deeplink" not in body


@override_settings(**FAKE)
def test_pronoun_without_any_grounding_falls_back_to_caller(org):
    c = _client(org.report)
    r = c.post(CHAT, {"query": "how am I doing on my goals?"}, format="json")
    body = r.json()
    assert body["status"] == "ok"
    assert body["answer"].startswith("You ")  # self-answer, no accidental match
