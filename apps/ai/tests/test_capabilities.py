"""
The capabilities surface (FINAL2 unit 2).

Two things are under test. That "what can you do?" is answered from the caller's ROLE
with no model call at all — it is the chip a new user clicks first, which made it the
most-asked question in the product and the one it made least sense to pay Gemini for.
And that the answer states the BOUNDARIES, not only the strengths: a user who is not told
what the assistant cannot do finds out by hitting it.
"""
import pytest
from django.test import override_settings

from apps.ai.agents.chat import chat_answer
from apps.ai.models import ChatSession
from apps.ai.providers import register_fake_output
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db
FAKE = {"LLM_PROVIDER": "apps.ai.providers.FakeLLMProvider"}


def _session(user):
    return ChatSession.objects.create(tenant_id=user.tenant_id, owner=user)


@pytest.fixture
def counting_classifier():
    """Counts classifier calls, so "no model call" is asserted rather than assumed."""
    from apps.ai.agents import chat as chat_mod

    calls = []

    def spy(prompt, model):
        calls.append(prompt)
        return {"intent": "general"}

    register_fake_output(chat_mod.AGENT_CODE, spy)
    yield calls
    register_fake_output(chat_mod.AGENT_CODE, chat_mod._fake)


@override_settings(**FAKE)
@pytest.mark.parametrize("query", [
    "what can you do?", "What can you do", "who are you?", "what can't you do?",
    "help", "what can I ask?", "who can I see?", "how do you work?",
])
def test_the_capability_question_costs_no_model_call(org, counting_classifier, query):
    with tenant_context(org.tenant):
        out = chat_answer(org.manager, query, session=_session(org.manager))

    assert out["intent"] == "capability", query
    assert counting_classifier == [], f"{query!r} spent a Gemini call it did not need"


@override_settings(**FAKE)
def test_a_real_question_containing_those_words_is_not_the_blurb(org, counting_classifier):
    """"What can you do about the goals?" is a question, not a request for the leaflet —
    the match is anchored on the whole message for exactly this reason."""
    with tenant_context(org.tenant):
        out = chat_answer(org.manager, "what can you do about my team's goals?",
                          session=_session(org.manager))

    assert out["intent"] != "capability"


@override_settings(**FAKE)
def test_the_answer_states_what_it_cannot_do(org):
    with tenant_context(org.tenant):
        answer = chat_answer(org.manager, "what can you do?",
                             session=_session(org.manager))["answer"].lower()

    assert "approve" in answer, "the approval gate is the boundary users hit first"
    assert "outside your access" in answer or "access" in answer
    assert "isn't about performance" in answer or "performance" in answer


@override_settings(**FAKE)
def test_a_manager_hears_about_the_team_and_an_employee_does_not(org):
    with tenant_context(org.tenant):
        manager = chat_answer(org.manager, "what can you do?",
                              session=_session(org.manager))["answer"]
        employee = chat_answer(org.report, "what can you do?",
                               session=_session(org.report))["answer"]

    assert "reports to you" in manager
    assert "only see your own data" in employee
    assert "reports to you" not in employee, "an employee must not be offered team powers"
