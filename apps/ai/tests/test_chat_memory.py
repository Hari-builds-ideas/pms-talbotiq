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
from apps.testsupport.factories import CycleFactory, ReviewFactory, UserFactory

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
def test_new_named_person_overrides_remembered_context(org):
    # Regression: after grounding person A, naming a DIFFERENT person by full name
    # must resolve to B — not stay on A via the earlier context (tester bug).
    with tenant_context(org.tenant):
        _name(org.report, "Rhea Report")
        # a SECOND report of the same manager (both in scope) with a distinct name
        bob = UserFactory(tenant=org.tenant, manager=org.manager,
                          role="EMPLOYEE", display_name="Bob Builder")
    c = _client(org.manager)
    r1 = c.post(CHAT, {"query": "how is Rhea Report doing on her goals?"}, format="json")
    sid = r1.json()["session_id"]
    assert "Rhea Report" in r1.json()["answer"]
    # Turn 2 — a NEW full name (with a pronoun too) must switch to Bob, not Rhea.
    r2 = c.post(CHAT, {"query": "Bob Builder how are his goals?", "session_id": sid}, format="json")
    body2 = r2.json()
    assert "Bob Builder" in body2["answer"]
    assert "Rhea Report" not in body2["answer"]
    # Turn 3 — a PURE pronoun (no name) still follows the last person (Bob).
    r3 = c.post(CHAT, {"query": "how are his goals?", "session_id": sid}, format="json")
    assert "Bob Builder" in r3.json()["answer"]


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
    # Named resolution matches Rhea tenant-wide, but she is outside the peer's
    # scope: an honest guardrail reply (no access, only admin/HR sees everyone) —
    # and, crucially, NO performance data leaked.
    ans = body["answer"].lower()
    assert "don't have access" in ans and "admin" in ans
    assert "goal(s):" not in body["answer"]


@override_settings(**FAKE)
def test_pronoun_after_out_of_scope_person_never_falls_back_to_self(org):
    """THE tester bug: an employee asks about someone out of scope (correct refusal),
    then a pronoun follow-up ("what about his reviews?") must STAY refused — it must
    never silently switch to the caller's OWN data. That looked like a data leak."""
    with tenant_context(org.tenant):
        _name(org.peer, "Pax Peer")  # out of the employee's scope
    c = _client(org.report)  # an EMPLOYEE (OWN scope)
    # Turn 1 grounds the CALLER as a person ref (the trap: a later pronoun must NOT
    # skip an out-of-scope person to land back on this self reference).
    r0 = c.post(CHAT, {"query": "how am I doing on my goals?"}, format="json")
    sid = r0.json()["session_id"]
    r1 = c.post(CHAT, {"query": "how is Pax Peer doing on his goals?", "session_id": sid}, format="json")
    assert "don't have access" in r1.json()["answer"].lower()
    r2 = c.post(CHAT, {"query": "what about his reviews?", "session_id": sid}, format="json")
    ans = r2.json()["answer"]
    # Did NOT answer about the caller: no self goals/counts dump.
    assert "goal(s)" not in ans and "no goals on record" not in ans and "review(s)" not in ans
    assert "don't have access" in ans.lower()  # still an honest refusal
    # And a further pronoun stays refused too — never a self goals dump.
    r3 = c.post(CHAT, {"query": "and how are his goals?", "session_id": sid}, format="json")
    assert "don't have access" in r3.json()["answer"].lower()
    assert "goal(s):" not in r3.json()["answer"]


@override_settings(**FAKE)
def test_bare_third_person_pronoun_with_no_referent_asks_who(org):
    """A 3rd-person pronoun with nothing grounded must ask who is meant — NOT dump
    the caller's own performance as if 'he' were the caller."""
    c = _client(org.report)
    r = c.post(CHAT, {"query": "how are his goals doing?"}, format="json")
    ans = r.json()["answer"]
    assert not ans.startswith("You ")
    assert "not sure who you mean" in ans.lower()


@override_settings(**FAKE)
def test_identical_full_names_disambiguate_by_email(org):
    """Two real people share a full name → the 'several match' reply must show their
    emails, not collapse to one useless entry that says 'several' but lists one."""
    with tenant_context(org.tenant):
        UserFactory(tenant=org.tenant, email="leon1@acme.test", role="EMPLOYEE",
                    display_name="Leon Petrova")
        UserFactory(tenant=org.tenant, email="leon2@acme.test", role="EMPLOYEE",
                    display_name="Leon Petrova")
    c = _client(org.admin)  # ADMIN sees everyone → both are in scope
    r = c.post(CHAT, {"query": "how is Leon Petrova doing on their goals?"}, format="json")
    ans = r.json()["answer"]
    assert "Several people match" in ans
    assert "leon1@acme.test" in ans and "leon2@acme.test" in ans


@override_settings(**FAKE)
def test_review_followup_answers_reviews_not_a_goals_dump(org):
    """"what about her reviews?" after grounding a person answers REVIEWS, not the
    default goals summary."""
    with tenant_context(org.tenant):
        _name(org.report, "Rhea Report")
        cycle = CycleFactory(tenant=org.tenant)
        ReviewFactory(tenant=org.tenant, employee=org.report, reviewer=org.manager, cycle=cycle)
    c = _client(org.manager)
    r1 = c.post(CHAT, {"query": "how is Rhea Report doing on her goals?"}, format="json")
    sid = r1.json()["session_id"]
    r2 = c.post(CHAT, {"query": "what about her reviews?", "session_id": sid}, format="json")
    ans = r2.json()["answer"]
    assert "review(s)" in ans
    assert "goal(s):" not in ans


@override_settings(**FAKE)
def test_manager_asking_outside_team_gets_guardrail_naming_who_they_can_see(org):
    """A manager who asks about someone NOT on their team is told plainly they
    don't have access (only admin/HR sees everyone) AND is shown who they CAN ask
    about — never a bare "no data" that reads like a bug, never a leak."""
    with tenant_context(org.tenant):
        _name(org.report, "Rhea Report")   # the manager's direct report
        _name(org.peer, "Pax Peer")        # reports to hrbp, NOT the manager
    c = _client(org.manager)
    r = c.post(CHAT, {"query": "how is Pax Peer doing on their goals?"}, format="json")
    body = r.json()
    assert body["status"] == "ok"
    ans = body["answer"]
    assert "don't have access" in ans.lower() and "admin" in ans.lower()
    assert "Rhea Report" in ans            # names who the manager CAN ask about
    assert "goal(s):" not in ans           # no performance data leaked


@override_settings(**FAKE)
def test_employee_asking_about_another_person_gets_self_only_guardrail(org):
    with tenant_context(org.tenant):
        _name(org.manager, "Meg Manager")
    c = _client(org.report)  # EMPLOYEE — OWN scope
    r = c.post(CHAT, {"query": "how is Meg Manager doing on her goals?"}, format="json")
    body = r.json()
    assert body["status"] == "ok"
    ans = body["answer"].lower()
    assert "don't have access" in ans and "your own" in ans
    assert "goal(s):" not in body["answer"]


@override_settings(**FAKE)
def test_full_name_never_resolves_to_a_same_surname_teammate(org):
    """Live-found bug: a manager asking about "Hugo O'Brien" (out of scope) must NOT
    silently resolve to a same-surname "Hana O'Brien" on their own team. A full name
    must FULLY match an in-scope person — otherwise it's an honest scope refusal."""
    with tenant_context(org.tenant):
        _name(org.report, "Hana O'Brien")  # the manager's report (in scope)
        UserFactory(tenant=org.tenant, manager=org.hrbp, role="EMPLOYEE",
                    display_name="Hugo O'Brien")  # out of the manager's scope
    c = _client(org.manager)
    r = c.post(CHAT, {"query": "how is Hugo O'Brien doing on his goals?"}, format="json")
    body = r.json()
    assert body["status"] == "ok"
    ans = body["answer"]
    assert "Hana O'Brien has" not in ans             # did NOT answer about the teammate
    assert "Hugo O'Brien" in ans                      # names the person actually asked for
    assert "don't have access" in ans.lower()         # honest scope refusal
    assert "goal(s):" not in ans


@override_settings(**FAKE)
def test_bare_first_name_resolves_to_the_one_on_your_team(org):
    """Scope-aware resolution: many people share a first name tenant-wide, but a
    manager asking "how is yuki doing?" gets the ONE Yuki on their team — not a
    disambiguation list of strangers they can't open."""
    with tenant_context(org.tenant):
        _name(org.report, "Yuki Onteam")  # the manager's report
        UserFactory(tenant=org.tenant, manager=org.hrbp, role="EMPLOYEE", display_name="Yuki Stranger")
        UserFactory(tenant=org.tenant, manager=org.hrbp, role="EMPLOYEE", display_name="Yuki Faraway")
    c = _client(org.manager)
    r = c.post(CHAT, {"query": "how is yuki doing on her goals?"}, format="json")
    body = r.json()
    assert body["status"] == "ok"
    assert "Yuki Onteam" in body["answer"]
    assert "Several people match" not in body["answer"]


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
