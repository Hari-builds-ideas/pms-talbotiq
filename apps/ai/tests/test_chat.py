"""
Chat Assistant — the safety-critical agent, over the REAL /api/ai/chat route with
the FakeLLMProvider. The HEADLINE proof: chat inherits the caller's RBAC and can
NEVER surface data the caller couldn't already see (an employee asking for a peer's
goals gets nothing — identical to a direct scoped API call); write/approval intents
are BLOCKED; the chat budget trips at 429; the entitlement gate denies a tenant
without the chat feature; no LLM provider → 503.
"""
import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.billing.models import AgentBudget, Entitlement
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, GoalFactory, UserFactory

pytestmark = pytest.mark.django_db

CHAT = "/api/ai/chat"
FAKE = {"LLM_PROVIDER": "apps.ai.providers.FakeLLMProvider"}


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _seed_goals(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        GoalFactory(employee=org.report, cycle=cycle, title="Report goal")
        GoalFactory(employee=org.peer, cycle=cycle, title="Peer goal")


@override_settings(**FAKE)
def test_employee_sees_own_goals(org):
    _seed_goals(org)
    resp = _client_for(org.report).post(CHAT, {"query": "show me my goals"}, format="json")
    assert resp.status_code == 200, resp.content
    assert "Report goal" in resp.json()["data"]


@override_settings(**FAKE)
def test_employee_cannot_see_a_peers_goals_via_chat(org):
    """HEADLINE: chat is RBAC-bound. An employee asking for a PEER's goals gets
    nothing — exactly like a direct scoped API call would."""
    _seed_goals(org)
    resp = _client_for(org.report).post(
        CHAT, {"query": f"show me {org.peer.email} goals"}, format="json"
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["data"] == []  # NO peer data leaked
    assert "Peer goal" not in str(body)
    # Honest guardrail: no access + only admin/HR sees everyone (never a leak).
    assert "don't have access" in body["answer"].lower()


@override_settings(**FAKE)
def test_manager_can_see_a_report_goals_via_chat(org):
    _seed_goals(org)
    resp = _client_for(org.manager).post(
        CHAT, {"query": f"show me {org.report.email} goals"}, format="json"
    )
    assert resp.status_code == 200, resp.content
    assert "Report goal" in resp.json()["data"]  # in the manager's scope


@override_settings(**FAKE)
def test_write_intent_returns_an_inert_plan(org):
    # AGENT_UX_V3 §A — a write now returns a PLAN (not a single proposal / blanket
    # block). It is INERT: creating it executes + audits NOTHING.
    from apps.audit.models import AuditLog

    with tenant_context(org.tenant):
        before = AuditLog.objects.count()
    resp = _client_for(org.manager).post(CHAT, {"query": "start a 360 for my report"}, format="json")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["type"] == "plan" and body["status"] == "plan" and body["intent"] == "write"
    assert isinstance(body["plan"]["steps"], list) and body["plan"]["summary"]
    assert body["session_id"]
    with tenant_context(org.tenant):
        # No write/approval audit rows from merely planning (feedback_cycle.created etc.).
        assert AuditLog.objects.filter(action="feedback_cycle.created").count() == 0
        assert AuditLog.objects.filter(action="goal.approved").count() == 0
        assert AuditLog.objects.count() == before


@override_settings(**FAKE)
def test_destructive_request_is_refused_and_writes_nothing(org):
    # BUGS_FOUND P0-1 — deletion is not an agent action; a bulk-destructive request is
    # refused EXPLICITLY (not turned into a plan/proposal), and nothing is created/deleted.
    from apps.audit.models import AuditLog
    from apps.identity.models import User

    with tenant_context(org.tenant):
        users_before = User.objects.count()
        audit_before = AuditLog.objects.count()
    for q in ("delete all the data", "erase all employees", "wipe the database"):
        resp = _client_for(org.manager).post(CHAT, {"query": q}, format="json")
        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert body["status"] == "blocked", (q, body)
        assert "can't delete" in body["answer"].lower()
        assert body.get("type") != "plan" and "plan" not in body
    with tenant_context(org.tenant):
        assert User.objects.count() == users_before   # nothing deleted
        assert AuditLog.objects.count() == audit_before  # nothing written


@override_settings(**FAKE)
def test_multi_intent_write_returns_multi_step_plan(org):
    # "start a 360 for Rhea and draft a review for Rhea" → a 2-step plan (both
    # actions the manager can do, with a draftable review present).
    from apps.testsupport.factories import ReviewFactory

    with tenant_context(org.tenant):
        org.report.display_name = "Rhea Report"
        org.report.save(update_fields=["display_name"])
        ReviewFactory(employee=org.report, cycle=CycleFactory(tenant=org.tenant, status="ACTIVE"), state="DRAFT")
    resp = _client_for(org.manager).post(
        CHAT, {"query": "start a 360 for Rhea and draft a review for Rhea"}, format="json"
    )
    assert resp.status_code == 200, resp.content
    steps = resp.json()["plan"]["steps"]
    assert [s["action"] for s in steps] == ["initiate_360", "draft_review"]
    assert all(s["feel"] == "confirm" and s["reason"] for s in steps)


# ── RW_BUILD_5: natural-language team search, surfaced through chat ──────────────


@override_settings(**FAKE)
def test_manager_team_search_via_chat(org):
    """A manager's 'find people' query routes through the deterministic, scope-bound
    NL search and returns the matching teammates in `data` (the fake classifies any
    search query to employees_missing_goals; report has no active goal → surfaces)."""
    with tenant_context(org.tenant):
        org.report.display_name = "Reza Report"
        org.report.save(update_fields=["display_name"])
    resp = _client_for(org.manager).post(
        CHAT, {"query": "who on my team is missing goals?"}, format="json"
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["intent"] == "search"
    assert "Reza Report" in body["data"]  # the report (no goal) surfaces, scope-bound


@override_settings(**FAKE)
def test_employee_team_search_is_not_exposed(org):
    """Team search is a manager/HR capability (VIEW_TEAM_SCORES). An employee's
    search-shaped query falls through to the general redirect — never the team path."""
    resp = _client_for(org.report).post(
        CHAT, {"query": "who on my team is missing goals?"}, format="json"
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["intent"] == "general"
    assert body["data"] == []


# ── ISSUE 2: precise write-refusals over the chat endpoint (not a blanket "read-only") ──


@override_settings(**FAKE)
def test_manager_jd_write_returns_empty_plan_not_silent(org):
    # A manager lacks the JD capability (HRBP+). The forbidden step is DROPPED at
    # plan-build (defense in depth) → an empty plan whose summary SAYS nothing could
    # be prepared (nothing silently dropped), without naming the capability.
    resp = _client_for(org.manager).post(CHAT, {"query": "create a JD for Staff Engineer"}, format="json")
    assert resp.status_code == 200 and resp.json()["status"] == "plan"
    body = resp.json()
    assert body["plan"]["steps"] == []  # the JD step the manager can't do was dropped
    assert body["plan"]["summary"]  # …but the summary is not silent


@override_settings(**FAKE)
def test_vague_followup_write_plans_nothing_and_asks(org):
    resp = _client_for(org.manager).post(CHAT, {"query": "now make the draft"}, format="json")
    assert resp.status_code == 200 and resp.json()["status"] == "plan"
    body = resp.json()
    assert body["plan"]["steps"] == []
    summary = body["plan"]["summary"].lower()
    assert "couldn't" in summary or "tell me" in summary


@override_settings(**FAKE)
def test_employee_succession_write_plan_does_not_reveal_it(org):
    # Employee lacks the succession capability → the step is dropped; the plan summary
    # must NOT reveal the sensitive feature exists.
    resp = _client_for(org.report).post(
        CHAT, {"query": "enrich the succession plan for VP Engineering"}, format="json"
    )
    assert resp.status_code == 200 and resp.json()["status"] == "plan"
    body = resp.json()
    assert body["plan"]["steps"] == []
    assert "succession" not in body["plan"]["summary"].lower()  # never reveal it


# ── BUG 4: intent is honoured — general/capability questions don't dump metrics ──


@override_settings(**FAKE)
def test_capability_question_describes_the_assistant_not_metrics(org):
    _seed_goals(org)
    resp = _client_for(org.report).post(CHAT, {"query": "what can you do?"}, format="json")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["intent"] == "capability"
    assert body["data"] == []  # NOT a performance dump
    assert "Report goal" not in str(body)
    # It describes ITSELF — what it can do and what it cannot. It used to have to say
    # "read-only"; that stopped being true when write actions landed as approval-gated
    # plans, so the assertion is on the substance (the approval boundary) rather than on
    # a self-description the product outgrew.
    answer = body["answer"].lower()
    assert "performance assistant" in answer
    assert "approve" in answer, "the approval gate is the boundary worth stating"


@override_settings(**FAKE)
@pytest.mark.parametrize("q", ["I feel lonely", "what day is today?", "tell me a joke"])
def test_general_question_gets_a_conversational_answer_not_metrics(org, q):
    _seed_goals(org)
    resp = _client_for(org.report).post(CHAT, {"query": q}, format="json")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["intent"] == "general"
    assert body["data"] == []  # the bug was: every query returned the goals/score dump
    assert "Report goal" not in str(body)


@override_settings(**FAKE)
def test_grounded_performance_question_still_answers_with_data(org):
    """The fix must NOT regress grounded answers: a performance question still
    returns the caller's scoped goals."""
    _seed_goals(org)
    resp = _client_for(org.report).post(CHAT, {"query": "how am I doing this cycle?"}, format="json")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["intent"] == "performance"
    assert "Report goal" in body["data"]


@override_settings(**FAKE)
def test_cross_tenant_target_returns_nothing(org, other_tenant):
    outsider = UserFactory(tenant=other_tenant, role="EMPLOYEE", email="out@other.test")
    resp = _client_for(org.manager).post(
        CHAT, {"query": f"show me {outsider.email} goals"}, format="json"
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["data"] == []  # cross-tenant target never resolves


@override_settings(**FAKE)
def test_chat_budget_trips_at_429(org):
    with tenant_context(org.tenant):
        AgentBudget.objects.create(tenant_id=org.tenant.id, agent_code="chat", window="DAILY", limit=1)
    client = _client_for(org.report)
    assert client.post(CHAT, {"query": "my goals"}, format="json").status_code == 200
    assert client.post(CHAT, {"query": "my goals"}, format="json").status_code == 429


@override_settings(**FAKE)
def test_tenant_without_chat_entitlement_is_403(org, other_tenant):
    # A tenant with an empty pack set does not hold the chat feature → 403.
    user = UserFactory(tenant=other_tenant, role="EMPLOYEE", email="nochat@other.test")
    with tenant_context(other_tenant):
        Entitlement.objects.create(tenant_id=other_tenant.id, seat_count=1, feature_packs=[])
    assert _client_for(user).post(CHAT, {"query": "my goals"}, format="json").status_code == 403


def test_unconfigured_llm_is_503(org):
    # No LLM_PROVIDER (default NotConfigured) → the chat surfaces a loud 503.
    resp = _client_for(org.report).post(CHAT, {"query": "my goals"}, format="json")
    assert resp.status_code == 503


def test_unauthenticated_is_401(org):
    assert APIClient().post(CHAT, {"query": "my goals"}, format="json").status_code == 401
