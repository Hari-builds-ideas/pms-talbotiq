"""
The conversation STATE MACHINE (AGENT_REBUILD/B) — multi-step tasks must actually
complete. These are the live-reproduced bugs that made the assistant "feel dumb":

  * Bug 1 — a pending follow-up question ("how are you feeling this week, 1–5?") was
    NEVER answerable: the slot-fill lived inside ``build_plan``, which is only reached
    when the LLM classifies the message as a WRITE. A bare "5" classifies as *general*,
    so the reply fell through to the read path and the SAME question came back, forever.
  * Bug 2 — "do the same for <someone else>" lost the ACTION and started a check-in.
  * Bug 3 — "make a recognition for X" could route to a check-in.
  * Bug 4 — there was no escape: a new command mid-pending was ignored, not obeyed.

Everything here goes through ``chat_answer`` — the ONE real send path the SPA uses —
because the defect was in the routing *before* the planner, not in the planner itself.
The deterministic FakeLLMProvider stands in for the model, exactly as it does live for
classification: no network, and the same non-write classification that caused the loop.
"""
import pytest
from django.test import override_settings

from apps.ai.agents.chat import chat_answer
from apps.ai.models import ChatSession, ChatTurn
from apps.checkins.models import CheckIn
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import UserFactory

pytestmark = pytest.mark.django_db
FAKE = {"LLM_PROVIDER": "apps.ai.providers.FakeLLMProvider"}


def _session(user):
    return ChatSession.objects.create(tenant_id=user.tenant_id, owner=user)


def _name(user, display):
    user.display_name = display
    user.save(update_fields=["display_name"])
    return user


def _say(user, session, text):
    """One full user turn through the real send path, recording both turns exactly as
    the view does — session memory is what the state machine reads."""
    from apps.ai import sessions as sess

    sess.append_turn(session, ChatTurn.Role.USER, text)
    result = chat_answer(user, text, session=session)
    plan = result.get("plan")
    answer = result.get("answer") or (plan.summary if plan is not None else "")
    refs = None
    if plan is not None:
        from apps.ai.planner import refs_for_plan

        refs = refs_for_plan(plan)
    sess.append_turn(session, ChatTurn.Role.ASSISTANT, answer, refs=refs, plan=plan)
    # The view surfaces a plan's summary as the spoken answer — mirror that, so a test
    # can assert on what the user actually reads regardless of which path replied.
    return {**result, "answer": answer}


def _steps(result):
    plan = result.get("plan")
    return list(plan.steps.all()) if plan is not None else []


def _actions(result):
    """Which ACTION each step belongs to. A clarify step reports the action it is
    gathering a detail for — "start my check-in" routed correctly even when the very
    next thing it does is ask for the mood."""
    return [
        (s.params or {}).get("clarify_action", s.action) if s.action == "clarify" else s.action
        for s in _steps(result)
    ]


# ── Bug 1 — the pending slot must actually capture the answer ────────────────────


@override_settings(**FAKE)
def test_pending_mood_slot_captures_a_bare_number(org):
    """THE worst bug: "start my check-in" asks for a mood, and the reply "5" must FILL
    that slot and produce the confirm step — not re-ask the same question."""
    with tenant_context(org.tenant):
        session = _session(org.report)
        asked = _say(org.report, session, "start my check-in")
        assert _steps(asked)[0].feel == "clarify"

        answered = _say(org.report, session, "5")
        steps = _steps(answered)
        assert [s.action for s in steps] == ["open_checkin"], (
            f"a bare mood answer must resume the check-in, got {_actions(answered)}"
        )
        assert steps[0].feel == "confirm", "the answered slot must produce a confirm step"
        assert steps[0].params["mood"] == 5


@override_settings(**FAKE)
def test_pending_mood_slot_accepts_a_worded_answer(org):
    """"good" is a real answer to "how are you feeling?" — it must fill the slot."""
    with tenant_context(org.tenant):
        session = _session(org.report)
        _say(org.report, session, "start my check-in")
        answered = _say(org.report, session, "feeling good")
        assert _actions(answered) == ["open_checkin"]
        assert _steps(answered)[0].params["mood"] == 4


@override_settings(**FAKE)
def test_mood_stated_up_front_never_asks(org):
    """"start my check-in, mood 4" carries the detail already — no question at all."""
    with tenant_context(org.tenant):
        session = _session(org.report)
        out = _say(org.report, session, "start my check-in, mood 4")
        assert _actions(out) == ["open_checkin"]
        assert _steps(out)[0].feel == "confirm"
        assert _steps(out)[0].params["mood"] == 4


@override_settings(**FAKE)
def test_invalid_answer_reasks_once_with_the_expected_format_then_gives_up(org):
    """"banana" is not a mood. Say WHY and re-ask ONCE; a second miss abandons the
    slot instead of looping forever."""
    with tenant_context(org.tenant):
        session = _session(org.report)
        _say(org.report, session, "start my check-in")

        first_miss = _say(org.report, session, "banana")
        assert _steps(first_miss) and _steps(first_miss)[0].feel == "clarify"
        assert "1" in first_miss["answer"] and "5" in first_miss["answer"], (
            "the re-ask must state the expected format"
        )

        second_miss = _say(org.report, session, "banana")
        assert not any(s.feel == "clarify" and s.action == "clarify" for s in _steps(second_miss)), (
            "a second invalid answer must NOT re-ask a third time — the loop is the bug"
        )


@override_settings(**FAKE)
def test_answered_checkin_actually_creates_the_checkin_on_approve(org):
    """End to end: ask → answer → approve → the check-in EXISTS (HITL gate intact:
    nothing was created before the explicit approve)."""
    from apps.ai.planner import approve_step

    with tenant_context(org.tenant):
        session = _session(org.report)
        _say(org.report, session, "start my check-in")
        answered = _say(org.report, session, "4")
        assert CheckIn.objects.filter(author_id=org.report.id).count() == 0, "HITL: inert until approved"

        step = _steps(answered)[0]
        approve_step(org.report, answered["plan"].id, step.id)
        ci = CheckIn.objects.filter(author_id=org.report.id).first()
        assert ci is not None and ci.mood == 4


# ── Bug 4 — the user can always escape a pending question ────────────────────────


@override_settings(**FAKE)
def test_new_command_mid_pending_abandons_and_starts_the_new_task(org):
    """Mid check-in, "make a recognition for Ingrid Garcia" must START THAT
    RECOGNITION — not be swallowed as a mood answer, not re-ask the question."""
    with tenant_context(org.tenant):
        _name(org.peer, "Ingrid Garcia")
        session = _session(org.manager)
        _say(org.manager, session, "start my check-in")

        out = _say(org.manager, session, "make a recognition for Ingrid Garcia")
        assert _actions(out) == ["give_recognition"], (
            f"a new command mid-pending must be obeyed, got {_actions(out)}"
        )
        assert _steps(out)[0].params["recipient_user_id"] == str(org.peer.id)


@override_settings(**FAKE)
def test_explicit_cancel_clears_the_pending_question(org):
    """"never mind" must clear the slot and say so — and NOT leave it armed."""
    with tenant_context(org.tenant):
        session = _session(org.report)
        _say(org.report, session, "start my check-in")

        cancelled = _say(org.report, session, "never mind")
        assert not _steps(cancelled), "cancel produces no new plan steps"
        assert "cancel" in cancelled["answer"].lower() or "dropped" in cancelled["answer"].lower()

        # The slot is really gone: a later bare "5" is NOT swallowed as a mood.
        after = _say(org.report, session, "5")
        assert _actions(after) != ["open_checkin"], "a cleared slot must not still capture"


# ── Bug 2 — "do the same for X" repeats the ACTION ───────────────────────────────


@override_settings(**FAKE)
def test_do_the_same_for_repeats_the_previous_action_for_a_new_person(org):
    """Recognition for one colleague, then "do the same for <another>" → a
    RECOGNITION for that other person (this used to start a check-in)."""
    with tenant_context(org.tenant):
        priya = _name(org.hrbp, "Priya Nair")
        ingrid = _name(org.peer, "Ingrid Garcia")
        session = _session(org.manager)

        first = _say(org.manager, session, "give recognition to Priya Nair for her excellent work")
        assert _actions(first) == ["give_recognition"]
        assert _steps(first)[0].params["recipient_user_id"] == str(priya.id)

        again = _say(org.manager, session, "do the same for Ingrid Garcia")
        assert _actions(again) == ["give_recognition"], (
            f'"do the same" must repeat the recognition, got {_actions(again)}'
        )
        assert _steps(again)[0].params["recipient_user_id"] == str(ingrid.id)


@override_settings(**FAKE)
def test_do_the_same_resolves_a_person_outside_the_callers_team(org):
    """"do the same for X" uses the COMPANY-WIDE directory, like the action it
    repeats — an out-of-team colleague must resolve."""
    with tenant_context(org.tenant):
        _name(org.report, "Rhea Report")
        outsider = UserFactory(
            tenant=org.tenant, role="EMPLOYEE", display_name="Lucas Schmidt",
            email="lucas@acme.test", manager=org.hrbp,
        )
        session = _session(org.manager)
        _say(org.manager, session, "give recognition to Rhea Report for shipping the migration")

        again = _say(org.manager, session, "same for Lucas Schmidt")
        assert _actions(again) == ["give_recognition"]
        assert _steps(again)[0].params["recipient_user_id"] == str(outsider.id)


# ── Bug 3 — every command routes to the action it names ──────────────────────────


@override_settings(**FAKE)
@pytest.mark.parametrize(
    "message,expected",
    [
        ("make a recognition for Ingrid Garcia", "give_recognition"),
        ("give recognition to Ingrid Garcia", "give_recognition"),
        ("kudos to Ingrid Garcia for the launch", "give_recognition"),
        ("shout out to Ingrid Garcia", "give_recognition"),
        ("praise Ingrid Garcia for her work", "give_recognition"),
        ("start my check-in", "open_checkin"),
        ("log my mood", "open_checkin"),
        ("draft a review for Ingrid Garcia", "draft_review"),
        ("start a 360 for Ingrid Garcia", "initiate_360"),
    ],
)
def test_each_intent_routes_to_the_action_it_names(org, message, expected):
    with tenant_context(org.tenant):
        # ONE Ingrid Garcia, inside the manager's team, so the scoped data actions
        # (draft a review, start a 360) and the tenant-wide one all reach her.
        _name(org.report, "Ingrid Garcia")
        from apps.testsupport.factories import CycleFactory, ReviewFactory

        cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
        ReviewFactory(employee=org.report, cycle=cycle, state="DRAFT")

        session = _session(org.manager)
        out = _say(org.manager, session, message)
        assert expected in _actions(out), (
            f"{message!r} must route to {expected}, got {_actions(out)}"
        )


# ── recognition keeps the reason the user actually gave ──────────────────────────


@override_settings(**FAKE)
def test_recognition_keeps_the_users_own_reason(org):
    """The category has to be one of the configured company values, so "for mentoring
    the new joiners" is filed under Teamwork. That must not throw the reason away: the
    note is free text and should say what the person actually said."""
    with tenant_context(org.tenant):
        _name(org.peer, "Ingrid Garcia")
        session = _session(org.manager)
        out = _say(org.manager, session,
                   "give recognition to Ingrid Garcia for mentoring the new joiners")
        step = _steps(out)[0]
        assert step.action == "give_recognition"
        assert "mentoring the new joiners" in step.params["note"]
        assert "mentoring the new joiners" in step.summary


@override_settings(**FAKE)
def test_recognition_without_a_reason_still_reads_sensibly(org):
    """"make a recognition for Ingrid Garcia" — the clause after "for" is the NAME, not
    a reason, and must not be echoed back as one."""
    with tenant_context(org.tenant):
        _name(org.peer, "Ingrid Garcia")
        session = _session(org.manager)
        out = _say(org.manager, session, "make a recognition for Ingrid Garcia")
        step = _steps(out)[0]
        assert step.action == "give_recognition"
        assert "Recognised for Ingrid" not in step.params["note"]
        assert step.params["note"] == "Recognised for Teamwork."
