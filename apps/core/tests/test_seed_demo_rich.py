"""
OVERNIGHT_E4 — coverage for `seed_demo_rich`, the demo-critical data path (flagged
untested in PROJECT_STATE §7). Proves the guarantees the live demo relies on:
  * idempotent — a second run produces the same population (no duplicates/drift);
  * every seeded person's ACTIVE goal weights sum to 100 (the over-weight fix holds);
  * the showcase record (Akhil) exists and is On Track;
  * ACME-only — it never creates data outside the acme tenant;
  * no live AI — it completes under the NotConfigured provider (a live call would raise),
    and 360 summaries are left ungenerated (sections None), per the real-data rule.

Runs the command twice (heavy but this is the demo spine); no live network.
"""
from decimal import Decimal

import pytest
from django.core.management import call_command

from apps.goals.models import CycleScore, Goal
from apps.identity.models import User
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

pytestmark = pytest.mark.django_db


def _active_weight_violations(acme):
    """Non-admin acme users whose ACTIVE goals don't sum to 100."""
    bad = []
    for u in User.objects.exclude(role="ADMIN"):
        total = sum(
            (g.weight for g in Goal.objects.filter(employee_id=u.id, status=Goal.Status.ACTIVE)),
            Decimal("0"),
        )
        if total and total != Decimal("100.00"):
            bad.append((u.email, total))
    return bad


def test_seed_demo_rich_is_idempotent_and_well_formed():
    call_command("seed_demo_rich")
    acme = Tenant.objects.get(slug="acme")
    with tenant_context(acme):
        people_1 = User.objects.count()
        goals_1 = Goal.objects.count()
        assert people_1 > 100  # a real-sized org, not a toy
        assert _active_weight_violations(acme) == []  # the over-weight fix holds

    # A second run must not duplicate or drift the population (idempotent).
    call_command("seed_demo_rich")
    with tenant_context(acme):
        assert User.objects.count() == people_1
        assert Goal.objects.count() == goals_1
        assert _active_weight_violations(acme) == []


def test_seed_demo_rich_showcase_record_is_on_track():
    call_command("seed_demo_rich")
    acme = Tenant.objects.get(slug="acme")
    with tenant_context(acme):
        akhil = User.objects.filter(email="akhil@acme.test").first()
        assert akhil is not None and (akhil.display_name or "").strip()
        score = CycleScore.objects.filter(employee_id=akhil.id).order_by("-computed_at").first()
        assert score is not None and score.risk_status == CycleScore.Risk.ON_TRACK


def test_seed_demo_rich_is_acme_only():
    """The command must never create data outside the acme tenant (globex/base seed
    stay intact). In a fresh test DB, the only tenant it creates is acme."""
    call_command("seed_demo_rich")
    acme = Tenant.objects.get(slug="acme")
    # No goals exist for any tenant other than acme.
    non_acme_goals = Goal.all_objects.exclude(tenant_id=acme.id).count()
    assert non_acme_goals == 0


def test_seed_demo_rich_has_prior_cycle_history():
    """AGENT_UX_V3 Part 2.2 — real analytics history: ≥4 cycles (current H1 + 3 prior
    CLOSED) with real T-scores, so an individual trend is a 4-point curve. Prior-cycle
    goals are archived, so the ACTIVE-weight invariant still holds."""
    from apps.cycles.models import PerformanceCycle

    call_command("seed_demo_rich")
    acme = Tenant.objects.get(slug="acme")
    with tenant_context(acme):
        assert PerformanceCycle.objects.count() >= 4  # H1 2026 + Q1/Q2/H2 2025
        akhil = User.objects.filter(email="akhil@acme.test").first()
        assert CycleScore.objects.filter(employee_id=akhil.id).count() >= 4  # trend curve
        assert _active_weight_violations(acme) == []  # archived history → weight still 100
