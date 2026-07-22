"""AGENT_INTEL increment 1 — data-grounded DIAGNOSIS + TEAM-SCAN.

The assistant no longer answers "does X need help?" with a flat goal list. It
reasons over real, RBAC-scoped cycle status + KPI attainment:
  * diagnosis of one person ("is X on track / does X need help") — grounded, and
    STILL scope-checked (a report can't diagnose a peer);
  * a team-scan ("who's behind on my team?") over the caller's OWN reports only;
  * coreference: "does she need help?" after naming someone diagnoses THAT person.
All deterministic (FakeLLMProvider) — no live calls.
"""
import datetime
from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, UserFactory

pytestmark = pytest.mark.django_db
FAKE = {"LLM_PROVIDER": "apps.ai.providers.FakeLLMProvider"}
CHAT = "/api/ai/chat"


def _client(user):
    access, _ = issue_tokens_for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return c


def _score(tenant, employee, *, risk="ON_TRACK", pace_behind=False, t_score="50"):
    from apps.goals.models import CycleScore

    cyc = CycleFactory(tenant=tenant)
    return CycleScore.objects.create(
        tenant_id=tenant.id, employee=employee, cycle=cyc,
        raw_score=Decimal("1"), z_score=Decimal("0"), t_score=Decimal(str(t_score)),
        cohort_size=5, risk_status=risk, pace_behind=pace_behind,
        computed_at=timezone.now(),
    )


def _goal_with_kpi(tenant, employee, title, *, target, actual, created_by):
    from apps.goals.models import Goal, Kpi, KpiMeasurement

    cyc = CycleFactory(tenant=tenant)
    g = Goal.objects.create(
        tenant_id=tenant.id, employee=employee, cycle=cyc, title=title,
        weight=Decimal("100.00"), status="ACTIVE", created_by=created_by,
    )
    k = Kpi.objects.create(
        tenant_id=tenant.id, goal=g, name="Attainment", weight=Decimal("100.00"),
        target_value=Decimal(str(target)), direction="INCREASING", unit="%", source="MANUAL",
    )
    KpiMeasurement.objects.create(
        tenant_id=tenant.id, kpi=k, value=Decimal(str(actual)),
        recorded_at=timezone.now(), source="MANUAL",
    )
    return g


@override_settings(**FAKE)
def test_diagnosis_reasons_over_kpi_attainment(org):
    with tenant_context(org.tenant):
        _name = org.report
        _name.display_name = "Ravi Report"
        _name.save(update_fields=["display_name"])
        _score(org.tenant, org.report, risk="AT_RISK", pace_behind=True)
        _goal_with_kpi(org.tenant, org.report, "Ship the H1 roadmap",
                       target=100, actual=55, created_by=org.manager)
    c = _client(org.manager)
    r = c.post(CHAT, {"query": "does Ravi Report need help with his goals?"}, format="json")
    body = r.json()
    assert body["status"] == "ok"
    ans = body["answer"]
    # Reasoned, not a flat list: names the weak KPI + the attainment number.
    assert "Ship the H1 roadmap" in ans
    assert "55%" in ans
    assert "need" in ans.lower()  # a help verdict


@override_settings(**FAKE)
def test_diagnosis_coreference_after_naming(org):
    with tenant_context(org.tenant):
        org.report.display_name = "Maya Report"
        org.report.save(update_fields=["display_name"])
        _score(org.tenant, org.report, risk="ON_TRACK", pace_behind=False)
        _goal_with_kpi(org.tenant, org.report, "Grow craft", target=100, actual=95,
                       created_by=org.manager)
    c = _client(org.manager)
    r1 = c.post(CHAT, {"query": "how is Maya Report doing on her goals?"}, format="json")
    sid = r1.json()["session_id"]
    r2 = c.post(CHAT, {"query": "does she need help?", "session_id": sid}, format="json")
    ans = r2.json()["answer"]
    assert "Maya Report" in ans          # "she" resolved to Maya
    assert "no extra help" in ans.lower()  # on track + strong KPI → no help needed


@override_settings(**FAKE)
def test_diagnosis_is_scope_checked(org):
    """A report asking to diagnose a PEER is refused — intelligence never bypasses RBAC."""
    with tenant_context(org.tenant):
        org.peer.display_name = "Pax Peer"
        org.peer.save(update_fields=["display_name"])
        _score(org.tenant, org.peer, risk="AT_RISK", pace_behind=True)
    c = _client(org.report)  # EMPLOYEE — cannot see the peer
    r = c.post(CHAT, {"query": "is Pax Peer at risk?"}, format="json")
    ans = r.json()["answer"]
    assert "don't have access" in ans.lower()
    assert "AT_RISK" not in ans and "at risk" not in ans.lower().replace("at risk?", "")


@override_settings(**FAKE)
def test_team_scan_lists_only_flagged_reports(org):
    with tenant_context(org.tenant):
        org.report.display_name = "Behind Bob"
        org.report.save(update_fields=["display_name"])
        _score(org.tenant, org.report, risk="AT_RISK", pace_behind=True)
        # a second, healthy report of the same manager
        ok = UserFactory(tenant=org.tenant, manager=org.manager, role="EMPLOYEE",
                         display_name="Fine Fiona")
        _score(org.tenant, ok, risk="ON_TRACK", pace_behind=False)
    c = _client(org.manager)
    r = c.post(CHAT, {"query": "who's behind on my team?"}, format="json")
    ans = r.json()["answer"]
    assert "Behind Bob" in ans
    assert "Fine Fiona" not in ans   # healthy report not flagged


@override_settings(**FAKE)
def test_team_scan_refused_for_individual_contributor(org):
    """An employee has no reports → honest 'no team', never another person's data."""
    c = _client(org.report)
    r = c.post(CHAT, {"query": "who's at risk on my team?"}, format="json")
    ans = r.json()["answer"]
    assert "no team" in ans.lower() or "don't have any reports" in ans.lower()


@override_settings(**FAKE)
def test_comparison_ranks_team_best_first(org):
    with tenant_context(org.tenant):
        org.report.display_name = "Star Performer"
        org.report.save(update_fields=["display_name"])
        _score(org.tenant, org.report, risk="ON_TRACK", t_score="80")
        weak = UserFactory(tenant=org.tenant, manager=org.manager, role="EMPLOYEE",
                           display_name="Weak Link")
        _score(org.tenant, weak, risk="AT_RISK", pace_behind=True, t_score="30")
    c = _client(org.manager)
    r = c.post(CHAT, {"query": "who is doing best on my team?"}, format="json")
    ans = r.json()["answer"]
    assert "couldn't find" not in ans.lower()   # no longer a dead reply
    # Best-first: the star ranks ahead of the weak link.
    assert ans.index("Star Performer") < ans.index("Weak Link")


@override_settings(**FAKE)
def test_aggregation_returns_counts_not_the_full_list(org):
    with tenant_context(org.tenant):
        _score(org.tenant, org.report, risk="AT_RISK", pace_behind=True)
        ok = UserFactory(tenant=org.tenant, manager=org.manager, role="EMPLOYEE",
                         display_name="Fine Fiona")
        _score(org.tenant, ok, risk="ON_TRACK", pace_behind=False)
    c = _client(org.manager)
    r = c.post(CHAT, {"query": "how many of my reports are behind?"}, format="json")
    ans = r.json()["answer"]
    assert "on track" in ans.lower() and "at risk" in ans.lower()  # a count summary
    assert "Fine Fiona" not in ans   # a count, NOT the name list


@override_settings(**FAKE)
def test_at_risk_scan_excludes_behind_only(org):
    """"who's at risk" (rating) must not sweep in people who are only behind pace."""
    with tenant_context(org.tenant):
        org.report.display_name = "Risk Ray"
        org.report.save(update_fields=["display_name"])
        _score(org.tenant, org.report, risk="AT_RISK", pace_behind=False)
        pacey = UserFactory(tenant=org.tenant, manager=org.manager, role="EMPLOYEE",
                            display_name="Pacey Pat")
        _score(org.tenant, pacey, risk="ON_TRACK", pace_behind=True)
    c = _client(org.manager)
    r = c.post(CHAT, {"query": "who is at risk on my team?"}, format="json")
    ans = r.json()["answer"]
    assert "Risk Ray" in ans
    assert "Pacey Pat" not in ans   # behind pace but ON_TRACK rating → not "at risk"


@override_settings(**FAKE)
def test_llm_phrasing_is_used_when_the_model_answers(org):
    """When a model returns a phrased answer, it's used verbatim — the LLM only
    rewords the grounded draft."""
    import apps.ai.providers as providers

    with tenant_context(org.tenant):
        org.report.display_name = "Ravi Report"
        org.report.save(update_fields=["display_name"])
        _score(org.tenant, org.report, risk="ON_TRACK")
        _goal_with_kpi(org.tenant, org.report, "Ship it", target=100, actual=90,
                       created_by=org.manager)
    providers.register_fake_output("chat_phrase", lambda prompt, model: {"answer": "PHRASED-OK"})
    try:
        c = _client(org.manager)
        r = c.post(CHAT, {"query": "does Ravi Report need help?"}, format="json")
        assert r.json()["answer"] == "PHRASED-OK"
    finally:
        providers._FAKE_OUTPUTS.pop("chat_phrase", None)


@override_settings(**FAKE, AGENT_INTEL_LLM_PHRASING=False)
def test_phrasing_disabled_falls_back_to_grounded_draft(org):
    with tenant_context(org.tenant):
        org.report.display_name = "Ravi Report"
        org.report.save(update_fields=["display_name"])
        _score(org.tenant, org.report, risk="AT_RISK", pace_behind=True)
        _goal_with_kpi(org.tenant, org.report, "Ship the roadmap", target=100, actual=40,
                       created_by=org.manager)
    c = _client(org.manager)
    r = c.post(CHAT, {"query": "does Ravi Report need help?"}, format="json")
    ans = r.json()["answer"]
    assert "40%" in ans and "Ship the roadmap" in ans  # the deterministic grounded draft


@override_settings(**FAKE)
def test_capability_answer_is_role_aware(org):
    mgr = _client(org.manager).post(CHAT, {"query": "what can you do?"}, format="json").json()["answer"]
    emp = _client(org.report).post(CHAT, {"query": "what can you do?"}, format="json").json()["answer"]
    assert "team" in mgr.lower() and ("who's behind" in mgr.lower() or "doing best" in mgr.lower())
    assert "only see your own" in emp.lower()
    assert mgr != emp   # not one scripted blurb for everyone
