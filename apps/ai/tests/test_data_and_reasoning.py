"""
Real data, real reasoning (AGENT_REBUILD/C) — and the one rule that makes the
assistant feel like it's listening: **never answer a real question with the leaflet.**

"I'm your read-only performance assistant, I can summarise…" is the right reply to
"what can you do?" and to a genuinely unparseable message. It is the WRONG reply to
"how is Ingrid doing?", and getting it was the single most common way the assistant
looked stupid — the user asked something specific and answerable and got a brochure.

The failure was never in the answering code, which is thorough. It was that a
misclassified question never reached it: the classifier labels a message `general` and
the blurb goes out before anything tries. So the tests here **force that
misclassification** with a classifier stub that calls everything `general`, then assert
a real answer still comes back. That is the actual live failure mode, reproduced.

Scope is asserted alongside every one of them: salvaging a question changes only WHICH
code path runs, never who may read what.
"""
import pytest
from django.test import override_settings

from decimal import Decimal

from django.utils import timezone

from apps.ai.agents.chat import _GENERAL_ANSWER, chat_answer
from apps.ai.models import ChatSession
from apps.ai.providers import register_fake_output
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, UserFactory

pytestmark = pytest.mark.django_db
FAKE = {"LLM_PROVIDER": "apps.ai.providers.FakeLLMProvider"}

#: The distinctive opening of the capability blurb — what must NOT come back.
#: The distinctive opening of the capability blurb — what must NOT come back in answer
#: to a real question. It no longer claims "read-only" (write actions land as
#: approval-gated plans, so that stopped being true); "performance assistant" is the part
#: that identifies the leaflet.
_BLURB_TELL = "performance assistant"


@pytest.fixture
def blind_classifier():
    """Force the worst case: a classifier that labels EVERY message `general`. This is
    the live failure mode — the model shrugs, and the blurb goes out before the
    answering code is ever consulted."""
    from apps.ai.agents import chat as chat_mod

    register_fake_output(chat_mod.AGENT_CODE, lambda prompt, model: {"intent": "general"})
    yield
    register_fake_output(chat_mod.AGENT_CODE, chat_mod._fake)  # restore for other tests


def _session(user):
    return ChatSession.objects.create(tenant_id=user.tenant_id, owner=user)


def _name(user, display):
    user.display_name = display
    user.save(update_fields=["display_name"])
    return user


def _with_real_data(tenant, employee, *, title, attainment, risk="AT_RISK", created_by=None):
    """Give someone genuine, checkable performance data to reason over: an active goal
    with a measured KPI, and a cycle score. The numbers differ per person on purpose —
    that's what lets a test tell a real answer from a template."""
    from apps.goals.models import CycleScore, Goal, Kpi, KpiMeasurement

    cycle = CycleFactory(tenant=tenant, status="ACTIVE")
    goal = Goal.objects.create(
        tenant_id=tenant.id, employee=employee, cycle=cycle, title=title,
        weight=Decimal("100.00"), status="ACTIVE", created_by=created_by or employee,
    )
    kpi = Kpi.objects.create(
        tenant_id=tenant.id, goal=goal, name="Attainment", weight=Decimal("100.00"),
        target_value=Decimal("100"), direction="INCREASING", unit="%", source="MANUAL",
    )
    KpiMeasurement.objects.create(
        tenant_id=tenant.id, kpi=kpi, value=Decimal(str(attainment)),
        recorded_at=timezone.now(), source="MANUAL",
    )
    CycleScore.objects.create(
        tenant_id=tenant.id, employee=employee, cycle=cycle,
        raw_score=Decimal("1"), z_score=Decimal("0"), t_score=Decimal(str(attainment)),
        cohort_size=5, risk_status=risk, pace_behind=(risk == "AT_RISK"),
        computed_at=timezone.now(),
    )
    return goal


def _answer(result):
    return (result.get("answer") or "").strip()


# ── the rule: an answerable question never gets the leaflet ──────────────────────


@override_settings(**FAKE)
def test_a_misclassified_person_question_is_still_answered(org, blind_classifier):
    """The headline case. The classifier shrugs; the user still gets their answer."""
    with tenant_context(org.tenant):
        _name(org.report, "Ingrid Garcia")
        _with_real_data(org.tenant, org.report, title="Migrate the billing service", attainment=49)

        out = chat_answer(org.manager, "how is Ingrid Garcia doing?", session=_session(org.manager))
        answer = _answer(out)
        assert _BLURB_TELL not in answer, f"answered a real question with the blurb: {answer!r}"
        assert "Ingrid" in answer


@override_settings(**FAKE)
def test_a_misclassified_own_data_question_is_still_answered(org, blind_classifier):
    with tenant_context(org.tenant):
        _with_real_data(org.tenant, org.report, title="Ship the search rewrite", attainment=61)

        out = chat_answer(org.report, "how am I doing this cycle?", session=_session(org.report))
        assert _BLURB_TELL not in _answer(out)


@override_settings(**FAKE)
def test_an_unknown_name_says_so_specifically_instead_of_deflecting(org, blind_classifier):
    """C §3: if a name didn't resolve, say THAT — don't change the subject to a list
    of things you can do. And name the person they actually typed."""
    with tenant_context(org.tenant):
        _name(org.report, "Ingrid Garcia")

        out = chat_answer(org.manager, "how is Zebediah Quartermain doing?", session=_session(org.manager))
        answer = _answer(out)
        assert _BLURB_TELL not in answer
        assert "zebediah" in answer.lower(), f"the failed name must be echoed: {answer!r}"
        assert "couldn't find" in answer.lower()


@override_settings(**FAKE)
def test_a_genuinely_general_message_still_gets_the_redirect(org, blind_classifier):
    """The salvage must not swallow everything: small talk is still small talk."""
    with tenant_context(org.tenant):
        _name(org.report, "Ingrid Garcia")
        for chatter in ("what day is today?", "I feel lonely", "tell me a joke"):
            out = chat_answer(org.manager, chatter, session=_session(org.manager))
            assert _answer(out) == _GENERAL_ANSWER.strip(), f"{chatter!r} → {_answer(out)!r}"


@override_settings(**FAKE)
def test_the_capability_question_still_gets_the_capability_answer(org):
    """The blurb keeps its actual job."""
    with tenant_context(org.tenant):
        out = chat_answer(org.manager, "what can you do?", session=_session(org.manager))
        assert out["intent"] == "capability"
        assert _BLURB_TELL in _answer(out)


# ── the answers are grounded in real rows, not a fixed sentence ──────────────────


@override_settings(**FAKE)
def test_the_answer_reflects_this_persons_actual_data(org):
    """Two people with different data must get materially different answers — the
    check that catches a template pretending to be an answer."""
    with tenant_context(org.tenant):
        struggling = _name(org.report, "Ingrid Garcia")
        thriving = UserFactory(tenant=org.tenant, role="EMPLOYEE", display_name="Lucas Schmidt",
                               email="lucas@acme.test", manager=org.manager)
        _with_real_data(org.tenant, struggling, title="Migrate the billing service", attainment=41)
        _with_real_data(org.tenant, thriving, title="Cut p99 latency", attainment=96,
                        risk="ON_TRACK")

        a = _answer(chat_answer(org.manager, "how is Ingrid Garcia doing?", session=_session(org.manager)))
        b = _answer(chat_answer(org.manager, "how is Lucas Schmidt doing?", session=_session(org.manager)))

        assert a != b, "identical text for different data is a template, not an answer"
        assert "Ingrid" in a and "Lucas" in b
        assert "Lucas" not in a and "Ingrid" not in b


@override_settings(**FAKE)
def test_comparing_two_people_returns_both_with_their_own_numbers(org):
    with tenant_context(org.tenant):
        one = _name(org.report, "Ingrid Garcia")
        two = UserFactory(tenant=org.tenant, role="EMPLOYEE", display_name="Lucas Schmidt",
                          email="lucas@acme.test", manager=org.manager)
        _with_real_data(org.tenant, one, title="Migrate the billing service", attainment=41)
        _with_real_data(org.tenant, two, title="Cut p99 latency", attainment=96,
                        risk="ON_TRACK")

        answer = _answer(chat_answer(org.manager, "compare Ingrid Garcia and Lucas Schmidt",
                                     session=_session(org.manager)))
        assert "Ingrid" in answer and "Lucas" in answer
        assert _BLURB_TELL not in answer


# ── salvaging a question widens nothing ──────────────────────────────────────────


@override_settings(**FAKE)
def test_an_out_of_scope_person_is_still_refused_when_the_question_is_salvaged(org, blind_classifier):
    """The important safety property: routing a misclassified question to the data
    path must not hand out data the caller could never see."""
    with tenant_context(org.tenant):
        hidden = _name(org.report, "Ingrid Garcia")  # the manager's report; invisible to `peer`
        _with_real_data(org.tenant, hidden, title="Migrate the billing service", attainment=41)

        out = chat_answer(org.peer, "how is Ingrid Garcia doing?", session=_session(org.peer))
        answer = _answer(out).lower()
        assert "41" not in answer and "at risk" not in answer and "billing" not in answer, (
            f"salvaging the question leaked out-of-scope data: {answer!r}"
        )


@override_settings(**FAKE)
def test_an_employee_search_question_is_not_salvaged_into_someone_elses_data(org, blind_classifier):
    """An employee asking a team-shaped question gets the honest redirect, not a
    report on themselves dressed up as a team answer, and never a colleague's data."""
    with tenant_context(org.tenant):
        colleague = _name(org.report, "Ingrid Garcia")
        _with_real_data(org.tenant, colleague, title="Migrate the billing service", attainment=41)

        answer = _answer(chat_answer(org.peer, "who on my team is behind?", session=_session(org.peer)))
        assert "Ingrid" not in answer and "41" not in answer
