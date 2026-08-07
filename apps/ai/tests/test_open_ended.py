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


# ── the trend class: the one place the agent overrides a real answer ─────────────


@override_settings(**FAKE)
def test_did_one_person_improve_gets_the_delta_not_a_status(org, team, script, blind_classifier):
    """"Did she get better?" used to come back with where she is now — at risk, behind
    pace — which is a true sentence and not the question. The deterministic diagnosis
    has no concept of movement, so trend questions get handed on."""
    rosa = team["rosa"]
    script += [
        {"tool_calls": [_call("find_people", query="Rosa Villalobos")]},
        {"tool_calls": [_call("compute_improvement", person_id=str(rosa.id))]},
        {"content": "Yes — Rosa Villalobos went from 38.0 in H1 to 62.0 in H2, up 24.0."},
    ]
    with tenant_context(org.tenant):
        out = chat_answer(org.manager, "did Rosa Villalobos get better this cycle?",
                          session=_session(org.manager))

    assert out["tools"] == ["find_people", "compute_improvement"]
    assert "24" in out["answer"]


@override_settings(**FAKE)
def test_the_deterministic_answer_survives_if_the_agent_adds_nothing(
        org, team, script, blind_classifier):
    """The override is one-way. When the agent produces nothing tool-grounded, the
    answer the deterministic path already had is what goes out — asking the agent must
    never be able to take an answer away."""
    with tenant_context(org.tenant):
        out = chat_answer(org.manager, "did Rosa Villalobos get better this cycle?",
                          session=_session(org.manager))

    assert "Rosa" in out["answer"], out["answer"]
    assert out["status"] == "ok"


@override_settings(**FAKE)
def test_a_write_is_never_second_guessed_by_the_trend_rule(org, team, script):
    """"log that Rosa improved" contains a trend word and is still a write."""
    from apps.ai.agents import chat as chat_mod

    register_fake_output(chat_mod.AGENT_CODE, lambda prompt, model: {"intent": "write"})
    script += [{"content": "Done."}]
    try:
        with tenant_context(org.tenant):
            out = chat_answer(org.manager, "recognise Rosa Villalobos for improving so much",
                              session=_session(org.manager))
    finally:
        register_fake_output(chat_mod.AGENT_CODE, chat_mod._fake)

    assert out["status"] == "plan"
    assert script, "the agent never got the turn"


@override_settings(**FAKE)
def test_the_signed_in_user_is_findable_as_me(org):
    """Every person tool takes a person_id, so without this the agent cannot ask about
    the caller at all — "have I improved?" has no name in it to look up."""
    from apps.ai.tools import ToolContext, find_people

    with tenant_context(org.tenant):
        out = find_people(ToolContext(caller=org.report), "me")

    assert out["people"][0]["person_id"] == str(org.report.id)
    assert out["ambiguous"] is False


@override_settings(**FAKE)
def test_an_invented_person_id_is_a_result_not_a_crash(org, team, script, blind_classifier):
    """A model that skips find_people invents an id. The live eval produced
    "jamal_whitfield_id", which the ORM rejects as a UUID — from inside a tool call, in
    the middle of a turn. It comes back as "no such person" now, so the model can
    correct itself instead of the request dying."""
    script += [
        {"tool_calls": [_call("get_person_overview", person_id="rosa_villalobos_id")]},
        {"tool_calls": [_call("compute_improvement", order="desc", limit=1)]},
        {"content": "Rosa Villalobos improved most, by 24.0 points."},
    ]
    with tenant_context(org.tenant):
        out = chat_answer(org.manager, "who improved most since last cycle?",
                          session=_session(org.manager))

    assert out["tools"] == ["get_person_overview", "compute_improvement"]
    assert "24" in out["answer"]

    from apps.ai.tools import ToolContext, get_person_overview

    with tenant_context(org.tenant):
        assert get_person_overview(ToolContext(caller=org.manager),
                                   "rosa_villalobos_id")["empty"] is True


@override_settings(**FAKE)
def test_a_failing_tool_is_reported_to_the_model_not_raised(org):
    """Whatever goes wrong inside a tool, the loop still has to hand the model
    something — a traceback is not an answer."""
    from apps.ai import tools as tools_mod
    from apps.ai.tools import ToolContext, run_tool

    def explode(ctx, **kwargs):
        raise RuntimeError("the database fell over")

    original = tools_mod.TOOLS["get_my_team"]
    tools_mod.TOOLS["get_my_team"] = (explode, original[1])
    try:
        with tenant_context(org.tenant):
            out = run_tool(ToolContext(caller=org.manager), "get_my_team", {})
    finally:
        tools_mod.TOOLS["get_my_team"] = original

    assert out == {"error": "get_my_team could not be completed: RuntimeError"}


@override_settings(**FAKE)
def test_a_colleague_is_not_resolved_to_the_caller_by_accident(org):
    """The self shortcut is anchored to the WHOLE query, so a name that merely contains
    "me" is looked up normally."""
    from apps.ai.tools import ToolContext, find_people

    with tenant_context(org.tenant):
        mei = UserFactory(tenant=org.tenant, role="EMPLOYEE", display_name="Mei Tanaka",
                          email="mei@acme.test", manager=org.manager)
        out = find_people(ToolContext(caller=org.manager), "Mei Tanaka")

    assert out["people"][0]["person_id"] == str(mei.id)


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
def test_a_pronoun_follow_up_reaches_the_agent_with_an_id_to_use(
        org, team, script, blind_classifier):
    """"Has that person improved?" has no name in it, so find_people has nothing to
    resolve. The people already discussed are handed to the model as ids — from the
    session's own access-rechecked refs, not a second resolver."""
    from apps.ai import sessions
    from apps.ai.models import ChatTurn

    rosa = team["rosa"]
    with tenant_context(org.tenant):
        session = _session(org.manager)
        sessions.append_turn(session, ChatTurn.Role.USER, "who is my weakest?")
        sessions.append_turn(
            session, ChatTurn.Role.ASSISTANT, "Rosa Villalobos.",
            refs=[{"type": "user", "id": str(rosa.id), "label": "Rosa Villalobos"}])

        known = chat_mod_known(org.manager, session)
        assert {p["id"] for p in known} == {str(rosa.id)}

        script += [
            {"tool_calls": [_call("compute_improvement", person_id=str(rosa.id))]},
            {"content": "Yes — that person went from 38.0 to 62.0, up 24.0."},
        ]
        out = chat_answer(org.manager, "has that person improved since last cycle?",
                          session=session)

    assert out["tools"] == ["compute_improvement"]
    assert "24" in out["answer"]


@override_settings(**FAKE)
def test_a_team_answer_grounds_the_people_it_named(org, team):
    """A ranking used to hand back a list of strings, so the conversation forgot
    everyone in it the moment it was sent. The live eval caught the cost: asked "who is
    my top performer?" and then "how many goals do they have?", the agent had no ids,
    spent all five tool calls on find_people against names it had read out of the
    previous turn's prose, and gave up asking the user to be more specific."""
    with tenant_context(org.tenant):
        out = chat_answer(org.manager, "who's my top performer?",
                          session=_session(org.manager))

    labels = [r["label"] for r in out["refs"]]
    assert labels == out["data"], "grounded in the order the answer named them"
    assert "Bram de Vries" in labels
    assert all(r["type"] == "user" and r["id"] for r in out["refs"])


@override_settings(**FAKE)
def test_a_ranking_then_a_follow_up_reaches_the_agent_with_ids(org, team, script,
                                                              blind_classifier):
    """The whole chain, as the eval ran it. Turn one is a deterministic ranking; turn
    two — "and how many goals do they have?" — has no name in it at all.

    Before the ranking grounded anybody, the conversation had forgotten every one of
    them: the agent got an empty id list, spent all five tool calls on find_people
    against names it had read out of the previous turn's prose, and answered "please
    specify which of the top performers you'd like to know about".

    What fixes it also means the AGENT is no longer needed here — with the people
    grounded, the existing pronoun path resolves "they" and answers directly. That is
    the better outcome, and it is what this asserts: the right person, by name, from
    whichever mechanism got there first."""
    from apps.ai import sessions
    from apps.ai.models import ChatTurn

    with tenant_context(org.tenant):
        session = _session(org.manager)
        sessions.append_turn(session, ChatTurn.Role.USER, "who's my top performer?")
        first = chat_answer(org.manager, "who's my top performer?", session=session)
        sessions.append_turn(session, ChatTurn.Role.ASSISTANT, first["answer"],
                             refs=first["refs"])

        known = chat_mod_known(org.manager, session)
        assert known, "the ranking's people must survive into the next turn"
        top = first["refs"][0]["label"]

        ranked = [r["label"] for r in first["refs"]]
        second = chat_answer(org.manager, "and how many goals do they have?",
                             session=session)
        third = chat_answer(org.manager, "how is the first one doing?", session=session)

    # "they" after a three-person list is genuinely ambiguous, and which of them the
    # session binds it to is a pre-existing choice (within a turn, the last ref wins —
    # right for a narrative answer, arbitrary for a ranking). What the grounding
    # guarantees is that it lands on somebody who was actually named, instead of a dead
    # end.
    assert any(name in second["answer"] for name in ranked), second["answer"]
    assert "specify" not in second["answer"].lower()

    # "the first one" is not ambiguous, and it now resolves — a ranked list is an
    # offered set, and before this it was three strings the conversation had forgotten.
    assert ranked[0] in third["answer"], f"{ranked[0]!r} not in {third['answer']!r}"


@override_settings(**FAKE)
def test_a_risk_scan_grounds_only_the_people_it_showed(org, org_big_team=None):
    """"…and 4 more" were never shown, so grounding them would let "the last one"
    resolve to somebody the user has not seen."""
    from apps.ai.agents import chat as chat_mod

    with tenant_context(org.tenant):
        cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
        for i in range(7):
            person = UserFactory(tenant=org.tenant, role="EMPLOYEE",
                                 display_name=f"Risky Person{i}",
                                 email=f"risky{i}@acme.test", manager=org.manager)
            _score(org.tenant, person, cycle, "30", risk="AT_RISK", behind=True)

        out = chat_answer(org.manager, "who on my team is at risk?",
                          session=_session(org.manager))

    shown = len(out["refs"])
    assert 0 < shown <= chat_mod._TEAM_LIST_CAP
    assert shown < len(out["data"]), "more were flagged than were named"
    for ref in out["refs"]:
        assert ref["label"] in out["answer"], f"{ref['label']} was grounded but not shown"


@override_settings(**FAKE)
def test_a_person_the_caller_can_no_longer_read_is_not_handed_to_the_model(org, team):
    """The id list is only a shortcut for LOOKUP. It re-checks access, so somebody who
    has moved out of the caller's scope since being discussed simply is not in it."""
    with tenant_context(org.tenant):
        session = _session(org.manager)
        moved = team["rosa"]
        from apps.ai import sessions
        from apps.ai.models import ChatTurn

        sessions.append_turn(session, ChatTurn.Role.USER, "how is Rosa doing?")
        sessions.append_turn(
            session, ChatTurn.Role.ASSISTANT, "Fine.",
            refs=[{"type": "user", "id": str(moved.id), "label": "Rosa Villalobos"}])
        assert chat_mod_known(org.manager, session)

        moved.manager = org.hrbp  # reassigned out of this manager's subtree
        moved.save(update_fields=["manager"])
        assert chat_mod_known(org.manager, session) == []


def chat_mod_known(caller, session):
    from apps.ai.agents.chat import _known_people

    return _known_people(caller, session)


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
