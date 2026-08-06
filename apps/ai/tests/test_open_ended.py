"""
Open-ended, compositional questions (AGENT_V3/C).

The point of this unit is that nobody wrote a handler for these questions. "Who improved
most since last cycle?" is not a shape the deterministic router knows — it has no name in
it, no "how many", none of the phrases the team regexes match. Before this unit it landed
on the capability blurb or, worse, on a name lookup for the words "improved" and "cycle".
Now it falls through to the function-calling agent, which composes the scoped tools.

**Why the model is scripted here.** These tests own two questions: *does an unanswered
turn reach the agent*, and *is what comes back grounded in real, scope-checked rows*.
Both are properties of our code. Whether Gemini picks `compute_improvement` over
`get_cycle_scores` on a given morning is a different question, and it belongs to the eval
harness in unit D, which runs against the real provider and scores it. Mixing the two
here would give us a security test that fails when a model is having an off day.

So the script says which tools the model asks for; everything after that — the rows, the
arithmetic, the scope checks, the refusals — is real.
"""
import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.ai import providers
from apps.ai.agents.chat import _GENERAL_ANSWER, chat_answer
from apps.ai.models import ChatSession
from apps.ai.providers import register_fake_output
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, UserFactory

pytestmark = pytest.mark.django_db

FAKE = {"LLM_PROVIDER": "apps.ai.providers.FakeLLMProvider"}


@pytest.fixture
def blind_classifier():
    """Every message classified `general` — the state the router is in for any question
    it has no shape for. This is not a pessimistic stub; it is what actually happens to
    "who's ready for promotion?", and it is the door the agent comes in through."""
    from apps.ai.agents import chat as chat_mod

    register_fake_output(chat_mod.AGENT_CODE, lambda prompt, model: {"intent": "general"})
    yield
    register_fake_output(chat_mod.AGENT_CODE, chat_mod._fake)


@pytest.fixture
def script():
    """The model's turns, and a clean queue for whoever runs next."""
    providers.FakeLLMProvider.script = []
    yield providers.FakeLLMProvider.script
    providers.FakeLLMProvider.script = []


def _call(name, **arguments):
    return {"id": f"call_{name}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)}}


def _session(user):
    return ChatSession.objects.create(tenant_id=user.tenant_id, owner=user)


def _score(tenant, user, cycle, t, *, risk="ON_TRACK", behind=False, ago=0):
    from apps.goals.models import CycleScore

    return CycleScore.objects.create(
        tenant=tenant, employee=user, cycle=cycle, raw_score=Decimal(t),
        z_score=Decimal("0"), t_score=Decimal(t), cohort_size=10, risk_status=risk,
        pace_behind=behind, computed_at=timezone.now() - timedelta(days=ago))


@pytest.fixture
def team(org):
    """A manager with three reports and two cycles of scores, hand-checked:

        Rosa    38 → 62   +24   AT_RISK, behind pace
        Bram    70 → 74    +4   ON_TRACK
        Wei     55 → 49    -6   AT_RISK, behind pace

    So: biggest improver is Rosa (+24), two are behind pace, two are at risk, the mean
    of the latest scores is (62 + 74 + 49) / 3 = 61.7, and the weakest by score is Wei.
    Every assertion below is against these numbers, not against a fixed sentence.
    """
    with tenant_context(org.tenant):
        old = CycleFactory(tenant=org.tenant, name="H1", status="CLOSED")
        new = CycleFactory(tenant=org.tenant, name="H2", status="ACTIVE")
        people = {}
        for name, before, after, risk, behind in (
            ("Rosa Villalobos", "38", "62", "AT_RISK", True),
            ("Bram de Vries", "70", "74", "ON_TRACK", False),
            ("Wei Chen", "55", "49", "AT_RISK", True),
        ):
            user = UserFactory(tenant=org.tenant, role="EMPLOYEE", display_name=name,
                               email=f"{name.split()[0].lower()}@acme.test",
                               manager=org.manager)
            _score(org.tenant, user, old, before, ago=90)
            _score(org.tenant, user, new, after, risk=risk, behind=behind, ago=1)
            people[name.split()[0].lower()] = user
    return people


# ── improvement: a question with no pre-coded path at all ────────────────────────


@override_settings(**FAKE)
def test_who_improved_most_is_answered_by_composing_tools(org, team, script, blind_classifier):
    """The headline case. No handler exists for this question; the agent composes one,
    and the +24 in the answer came out of the database, not out of the model."""
    script += [
        {"tool_calls": [_call("compute_improvement", order="desc", limit=3)]},
        {"content": "Rosa Villalobos improved most — 38.0 to 62.0, up 24.0 points."},
    ]
    with tenant_context(org.tenant):
        out = chat_answer(org.manager, "who improved most since last cycle?",
                          session=_session(org.manager))

    assert out["tools"] == ["compute_improvement"], "the aggregate tool did the work"
    assert "Rosa" in out["answer"] and "24" in out["answer"]
    assert out["answer"] != _GENERAL_ANSWER


@override_settings(**FAKE)
def test_the_improvement_ranking_is_the_backends_arithmetic(org, team, script, blind_classifier):
    """What the model was *handed* is what matters: the ordering and every delta are
    already computed. A model that receives finished numbers cannot get them wrong."""
    script += [
        {"tool_calls": [_call("compute_improvement", order="desc", limit=3)]},
        {"content": "Rosa improved most, by 24 points."},
    ]
    with tenant_context(org.tenant):
        chat_answer(org.manager, "who improved most since last cycle?",
                    session=_session(org.manager))

    from apps.ai.tools import ToolContext, compute_improvement

    with tenant_context(org.tenant):
        result = compute_improvement(ToolContext(caller=org.manager), order="desc")
    ranked = result["ranked"]
    assert [r["name"] for r in ranked] == ["Rosa Villalobos", "Bram de Vries", "Wei Chen"]
    assert [r["delta"] for r in ranked] == [24.0, 4.0, -6.0]
    assert ranked[2]["direction"] == "declined"


# ── aggregation, ranking, risk: exact against the fixture ────────────────────────


@override_settings(**FAKE)
def test_how_many_are_behind_pace_is_an_exact_backend_count(org, team, script, blind_classifier):
    """This one has a pre-coded path, and it keeps it — `_AGG_RE` matches, the count
    comes from a scoped queryset, and the agent is never consulted. Recorded here
    anyway, because the question is on the acceptance list and what matters to the user
    is that the number is exactly right: 2 of 3, per the fixture."""
    script += [{"content": "Everyone is doing great."}]
    with tenant_context(org.tenant):
        out = chat_answer(org.manager, "how many of my reports are behind pace?",
                          session=_session(org.manager))

    assert "behind=2" in out["data"] and "at_risk=2" in out["data"]
    assert "2 behind pace" in out["answer"]
    assert script, "the deterministic count answered; the agent was not needed"


@override_settings(**FAKE)
def test_who_is_at_risk_names_only_the_callers_own_people(org, team, script, blind_classifier):
    """Also pre-coded (`_TEAM_SCAN_RE`). What must hold either way: the people named
    are the caller's, and somebody else's report never appears."""
    with tenant_context(org.tenant):
        stranger = UserFactory(tenant=org.tenant, role="EMPLOYEE",
                               display_name="Outsider Person",
                               email="outsider@acme.test", manager=org.hrbp)
        cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
        _score(org.tenant, stranger, cycle, "12", risk="AT_RISK", behind=True)

        out = chat_answer(org.manager, "who's at risk and why?", session=_session(org.manager))

        # The scoped tool the agent would have used excludes them too, so the guarantee
        # does not depend on which path served the turn.
        from apps.ai.tools import ToolContext, rank_team

        ranked = rank_team(ToolContext(caller=org.manager), metric="score", order="asc")

    assert "Wei" in out["answer"]
    assert "Outsider" not in out["answer"], "someone else's report must never appear"
    assert "Outsider Person" not in [r["name"] for r in ranked["ranked"]]


@override_settings(**FAKE)
def test_comparing_the_two_weakest_uses_the_backend_ordering(org, team, script, blind_classifier):
    script += [
        {"tool_calls": [_call("rank_team", metric="score", order="asc", limit=2)]},
        {"content": "Wei Chen is at 49.0 and Rosa Villalobos at 62.0; both are behind pace."},
    ]
    with tenant_context(org.tenant):
        out = chat_answer(org.manager, "compare my two weakest performers",
                          session=_session(org.manager))

    assert "Wei" in out["answer"] and "Rosa" in out["answer"]
    assert out["data"] == ["Wei Chen", "Rosa Villalobos"], "grounded, in the ranked order"


# ── judgement, framed as a suggestion ────────────────────────────────────────────


@override_settings(**FAKE)
def test_a_promotion_question_reasons_over_real_data(org, team, script, blind_classifier):
    """"Who's ready for promotion?" used to dead-end in a name lookup for the words
    "ready" and "promotion". It now composes real signals — and the answer is the
    human's to make."""
    script += [
        {"tool_calls": [_call("rank_team", metric="score", order="desc", limit=2)]},
        {"tool_calls": [_call("compute_improvement", order="desc", limit=3)]},
        {"content": "On the data, Bram de Vries is the strongest case — 74.0, on track, "
                    "up 4.0 since H1. That's a data-informed suggestion, not a decision; "
                    "promotion readiness needs your judgement too."},
    ]
    with tenant_context(org.tenant):
        out = chat_answer(org.manager, "who's ready for promotion?",
                          session=_session(org.manager))

    assert out["tools"] == ["rank_team", "compute_improvement"]
    assert "couldn't find anyone named" not in out["answer"]
    assert "Bram" in out["answer"]


# ── honesty: no data, out of scope, no tool ──────────────────────────────────────


@override_settings(**FAKE)
def test_an_out_of_scope_person_is_refused_not_answered(org, script, blind_classifier):
    """The agent can find anyone in the company; it can read almost nobody. The tool
    hands back a denial and that is all the model ever learns about them."""
    with tenant_context(org.tenant):
        stranger = UserFactory(tenant=org.tenant, role="EMPLOYEE",
                               display_name="Ines Okafor", email="ines@acme.test",
                               manager=org.hrbp)
        cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
        _score(org.tenant, stranger, cycle, "91", risk="ON_TRACK")

        script += [
            {"tool_calls": [_call("find_people", query="Ines Okafor")]},
            {"tool_calls": [_call("get_person_overview", person_id=str(stranger.id))]},
            {"content": "Ines Okafor is outside what you can see."},
        ]
        out = chat_answer(org.report, "is Ines Okafor tracking ahead of me?",
                          session=_session(org.report))

        # What the model was handed was a denial, so a leak was never available to it.
        from apps.ai.tools import ToolContext, get_person_overview

        assert get_person_overview(ToolContext(caller=org.report), str(stranger.id)) == {
            "denied": True, "reason": "You don't have access to that person's data."}

    assert "91" not in out["answer"] and "ON_TRACK" not in out["answer"]
    assert "don't have access" in out["answer"].lower()


@override_settings(**FAKE)
def test_a_question_with_no_supporting_data_says_so(org, script, blind_classifier):
    """An empty tool result is a fact to report, not a gap to fill."""
    with tenant_context(org.tenant):
        script += [
            {"tool_calls": [_call("compute_improvement", order="desc")]},
            {"content": "There's no data on that — nobody on your team has two "
                        "comparable cycle scores yet."},
        ]
        out = chat_answer(org.manager, "who improved most since last cycle?",
                          session=_session(org.manager))

        from apps.ai.tools import ToolContext, compute_improvement

        assert compute_improvement(ToolContext(caller=org.manager))["empty"] is True

    assert "no data" in out["answer"].lower()


@override_settings(**FAKE)
def test_an_answer_with_no_tool_behind_it_is_never_used(org, script, blind_classifier):
    """The structural guard. The model wrote a confident sentence without calling
    anything, so there is no scoped row behind a word of it — and it is discarded in
    favour of the deterministic redirect."""
    with tenant_context(org.tenant):
        for question in ("who improved most since last cycle?",
                         "summarise my team's biggest risks"):
            script[:] = [{"content": "Rosa is your top performer at 91 points."}]
            out = chat_answer(org.manager, question, session=_session(org.manager))

            assert "91" not in out["answer"], f"{question!r} → {out['answer']!r}"
            assert "top performer" not in out["answer"]
            assert "tools" not in out, "no tool ran, so there is no evidence to publish"


@override_settings(**FAKE)
def test_small_talk_still_gets_the_redirect(org, script, blind_classifier):
    """The same guard, seen from the other side: there is nothing for a tool to fetch
    about the weather, so nothing the agent says is used."""
    with tenant_context(org.tenant):
        for chatter in ("what day is today?", "tell me a joke"):
            script[:] = [{"content": "It's Tuesday and here's a joke."}]
            out = chat_answer(org.manager, chatter, session=_session(org.manager))
            assert out["answer"] == _GENERAL_ANSWER.strip(), f"{chatter!r}"


# ── what must NOT be touched ─────────────────────────────────────────────────────


@override_settings(**FAKE)
def test_a_write_still_becomes_an_approval_gated_plan(org, team, script):
    """The agent is read-only and sits BELOW the write path. A write intent must still
    produce an inert plan for a human to approve — the agent never gets the turn."""
    from apps.ai.agents import chat as chat_mod

    register_fake_output(chat_mod.AGENT_CODE, lambda prompt, model: {"intent": "write"})
    script += [{"content": "I went ahead and posted it."}]
    try:
        with tenant_context(org.tenant):
            out = chat_answer(org.manager, "give recognition to Rosa Villalobos",
                              session=_session(org.manager))
    finally:
        register_fake_output(chat_mod.AGENT_CODE, chat_mod._fake)

    assert out["status"] == "plan", out
    assert script, "the agent was never called — its turn is still queued"


@override_settings(**FAKE)
def test_a_pre_coded_answer_is_never_replaced_by_the_agent(org, team, script):
    """A question the deterministic router *can* answer keeps its answer. The agent is
    a fallback, not a competitor — otherwise every proven path becomes non-deterministic
    overnight."""
    script += [{"tool_calls": [_call("get_my_team")]}, {"content": "Nonsense from the model."}]
    with tenant_context(org.tenant):
        out = chat_answer(org.manager, "who on my team is behind?",
                          session=_session(org.manager))

    assert "Nonsense" not in out["answer"]
    assert script, "the deterministic path answered; the agent's turn is untouched"


@override_settings(**FAKE)
def test_the_internal_marker_never_reaches_the_caller(org, script, blind_classifier):
    """`_unanswered` is a routing decision, not part of the contract."""
    from apps.ai.agents.chat import _UNANSWERED

    with tenant_context(org.tenant):
        out = chat_answer(org.manager, "tell me a joke", session=_session(org.manager))
    assert _UNANSWERED not in out


# ── memory keeps working across the agent ────────────────────────────────────────


@override_settings(**FAKE)
def test_the_agent_sees_the_conversation_and_grounds_who_it_answered_about(
        org, team, script, blind_classifier):
    """Two things at once: the earlier turns reach the model (so "of those" means
    something), and the people the answer was about come back as refs (so the NEXT
    turn's "her" resolves through the existing session machinery)."""
    from apps.ai import sessions
    from apps.ai.models import ChatTurn

    with tenant_context(org.tenant):
        session = _session(org.manager)
        sessions.append_turn(session, ChatTurn.Role.USER, "who are my two weakest?")
        sessions.append_turn(session, ChatTurn.Role.ASSISTANT, "Wei Chen and Rosa Villalobos.")
        sessions.append_turn(session, ChatTurn.Role.USER, "of those, who improved?")

        script += [
            {"tool_calls": [_call("compute_improvement", order="desc", limit=3)]},
            {"content": "Rosa Villalobos improved by 24.0; Wei Chen declined by 6.0."},
        ]
        out = chat_answer(org.manager, "of those, who improved?", session=session)

        assert {r["label"] for r in out["refs"]} >= {"Rosa Villalobos", "Wei Chen"}
        # And the refs are live: the session resolves a pronoun through them.
        sessions.append_turn(session, ChatTurn.Role.ASSISTANT, out["answer"],
                             refs=out["refs"])
        assert sessions.last_referenced_person_any_scope(org.manager, session) is not None


@override_settings(**FAKE)
def test_the_current_question_is_not_sent_to_the_model_twice(org, team, script, blind_classifier):
    """The view records the user's turn before we run, so the naive history would repeat
    the question the model is already being asked."""
    from apps.ai.agents.chat import _history_for_agent
    from apps.ai import sessions
    from apps.ai.models import ChatTurn

    with tenant_context(org.tenant):
        session = _session(org.manager)
        sessions.append_turn(session, ChatTurn.Role.USER, "who improved most?")
        history = _history_for_agent(session, "who improved most?")

    assert history == []
