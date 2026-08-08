"""
The FINAL2 prompt bank, as a test (no API key, no spend).

`scripts/agent_selftest.py` runs the bank against a seeded tenant for a human to read.
This runs the same bank in CI against the ordinary fixture, so the routing it checks —
no self-deflection, no leak, refusals clean, writes still gated — cannot regress
unnoticed between manual runs.

Answer QUALITY is not in scope here and cannot be: the questions only the
function-calling agent can answer need a live model, and without one its reply is
discarded for not being tool-grounded. Those cases are marked `needs_agent` in the bank
and are checked for routing only. What is asserted for every prompt, agent or not, is
the part that is ours and deterministic.
"""
import json
import os

import pytest
from django.test import override_settings

from apps.ai.models import ChatSession, ChatTurn
from apps.ai.sessions import append_turn
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db
FAKE = {"LLM_PROVIDER": "apps.ai.providers.FakeLLMProvider"}

BANK = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))), "docs", "FINAL2", "test_bank.jsonl")


def _bank():
    rows = []
    with open(BANK) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "_comment" not in row:
                rows.append(row)
    return rows


CASES = _bank()


def test_the_bank_covers_every_category_it_claims_to():
    """A bank that quietly lost a category would keep passing while testing less."""
    cats = {c["cat"] for c in CASES}
    assert len(CASES) >= 50, f"the bank shrank to {len(CASES)} prompts"
    for required in ("self status", "single person", "team rank/compare",
                     "improvement/trend", "aggregation", "risk/diagnosis",
                     "readiness/judgement", "memory/follow-up", "out-of-scope",
                     "injection", "sql/technical", "write actions", "small talk",
                     "unknown/typo", "capability"):
        assert required in cats, f"category {required!r} vanished from the bank"


@pytest.fixture
def bank_actors(org):
    """The roles the bank asks as, plus somebody the manager genuinely cannot read."""
    from apps.rbac.scope import actor_can_access
    from apps.testsupport.factories import UserFactory

    with tenant_context(org.tenant):
        org.manager.display_name = "Mona Manager"
        org.manager.save(update_fields=["display_name"])
        org.report.display_name = "Rhea Report"
        org.report.save(update_fields=["display_name"])
        second = UserFactory(tenant=org.tenant, role="EMPLOYEE", display_name="Sam Second",
                             email="sam2@acme.test", manager=org.manager)
        stranger = UserFactory(tenant=org.tenant, role="EMPLOYEE",
                               display_name="Otto Outsider", email="otto2@acme.test",
                               manager=org.hrbp)
        assert not actor_can_access(org.manager, stranger)
    return {"manager": org.manager, "employee": org.report, "hrbp": org.hrbp,
            "_reports": [org.report, second], "_stranger": stranger}


def _fill(text, a):
    reports = a["_reports"]
    return (text
            .replace("{report2}", reports[1].display_name)
            .replace("{report}", reports[0].display_name)
            .replace("{stranger}", a["_stranger"].display_name)
            .replace("{typo}", "Rhea Reprot")
            .replace("{duplicate}", reports[0].display_name))


def _say(user, session, text):
    from apps.ai.agents.chat import chat_answer
    from apps.ai.planner import refs_for_plan

    append_turn(session, ChatTurn.Role.USER, text)
    result = chat_answer(user, text, session=session)
    plan = result.get("plan")
    answer = result.get("answer") or (plan.summary if plan is not None else "")
    append_turn(session, ChatTurn.Role.ASSISTANT, answer,
                refs=result.pop("refs", None) or (refs_for_plan(plan) if plan else None),
                plan=plan)
    return {**result, "answer": answer}


@override_settings(**FAKE)
@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_every_prompt_routes_correctly(org, bank_actors, case):
    from apps.ai.selftest import check_scope, judge

    actor = bank_actors[case["as"]]
    with tenant_context(org.tenant):
        session = ChatSession.objects.create(tenant_id=actor.tenant_id, owner=actor)
        question = _fill(case["q"], bank_actors)
        out = _say(actor, session, question)
        for follow in case.get("then", []):
            out = _say(actor, session, _fill(follow, bank_actors))
        answer = out.get("answer") or ""

        ok, why = judge(case, out, answer, bank_actors, live=False)
        assert ok, f"{case['id']} ({case['cat']}): {why}\n  q: {question}\n  a: {answer[:200]}"

        scope_ok, scope_why = check_scope(answer, actor, asked=question)
        assert scope_ok, f"{case['id']}: {scope_why}\n  a: {answer[:200]}"
