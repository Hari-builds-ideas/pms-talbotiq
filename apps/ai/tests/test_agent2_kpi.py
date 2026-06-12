"""
Agent 2 — KPI Intelligence (Fast). Deterministic nudge rules + best-effort Slack
delivery (Module 12) + the manager-dashboard read. It NEVER mutates scoring.
"""
from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.ai.agents import kpi
from apps.goals.models import CycleScore
from apps.integrations.models import TenantIntegration
from apps.integrations.tests.fakes import reset_slack, slack_sent
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory

pytestmark = pytest.mark.django_db
SLACK_FAKE = {"SLACK_CLIENT_FACTORY": "apps.integrations.tests.fakes.build_fake_slack_client"}


# ── nudge rules ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "risk, days, expected",
    [
        ("ON_TRACK", 60, None),
        ("CRITICAL", 60, "CRITICAL"),
        ("AT_RISK", 60, "STANDARD"),
        ("AT_RISK", 10, "SUPPRESSED"),   # ≤14 days left → suppress + warning
        ("AT_RISK", 14, "SUPPRESSED"),   # boundary
        ("AT_RISK", 15, "STANDARD"),
    ],
)
def test_classify_nudge_rules(risk, days, expected):
    nudge = kpi.classify_nudge(risk, days)
    assert (nudge["level"] if nudge else None) == expected


# ── delivery (Slack, best-effort) ───────────────────────────────────────────


def _enable_slack(tenant):
    with tenant_context(tenant):
        TenantIntegration.objects.create(tenant_id=tenant.id, kind="SLACK", enabled=True, config={"channel": "#kpi"})


@override_settings(**SLACK_FAKE)
def test_run_kpi_nudges_delivers_for_risk_only(tenant):
    reset_slack()
    _enable_slack(tenant)
    cycle = CycleFactory(tenant=tenant, status="ACTIVE", end_date=timezone.now().date() + timezone.timedelta(days=60))
    scores = [
        {"employee_id": "e1", "risk_status": "ON_TRACK"},   # no nudge
        {"employee_id": "e2", "risk_status": "AT_RISK"},    # STANDARD
        {"employee_id": "e3", "risk_status": "CRITICAL"},   # CRITICAL
    ]
    result = kpi.run_kpi_nudges(str(tenant.id), str(cycle.id), scores)
    assert result == {"considered": 3, "delivered": 2}
    sent = slack_sent()
    assert len(sent) == 2
    assert any("CRITICAL" in s["text"] for s in sent)


@override_settings(**SLACK_FAKE)
def test_signal_recompute_fires_nudges(org):
    """The full chain: a Module-2 recompute fires cycle_scores_recomputed → the
    Agent-2 receiver delivers nudges (best-effort)."""
    reset_slack()
    _enable_slack(org.tenant)
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE", end_date=timezone.now().date() + timezone.timedelta(days=60))
    # A worsening score → the receiver will nudge on recompute.
    from apps.goals.signals import cycle_scores_recomputed

    cycle_scores_recomputed.send(
        sender=None, tenant_id=str(org.tenant.id), cycle_id=str(cycle.id),
        scores=[{"employee_id": str(org.report.id), "risk_status": "CRITICAL"}],
    )
    assert len(slack_sent()) == 1


# ── manager dashboard read (scoped, read-only) ──────────────────────────────


def test_manager_nudges_lists_reports_at_risk(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE", end_date=timezone.now().date() + timezone.timedelta(days=60))
    with tenant_context(org.tenant):
        CycleScore.objects.create(
            tenant_id=org.tenant.id, employee=org.report, cycle=cycle,
            raw_score=Decimal("0"), z_score=Decimal("0"), t_score=Decimal("35"),
            cohort_size=10, risk_status="AT_RISK", computed_at=timezone.now(),
        )
        nudges = kpi.manager_nudges(org.manager)
    assert any(n["employee"] == str(org.report.id) and n["level"] == "STANDARD" for n in nudges)
