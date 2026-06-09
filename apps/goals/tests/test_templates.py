"""
KPI templates: the per-role catalogue's weight invariant, idempotent
tenant-scoped seeding, instantiation into a weight-complete Goal, and the
``seed_kpi_templates`` management command.
"""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command

from apps.goals.models import Goal, Kpi, KpiTemplate
from apps.goals.templates import (
    DEFAULT_TEMPLATES,
    instantiate_role_templates,
    instantiate_templates,
    seed_templates_for_tenant,
)
from apps.goals.validators import assert_kpi_weights_complete
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import (
    CycleFactory,
    KpiTemplateFactory,
    TenantFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

# Total number of catalogue entries across all roles.
_TOTAL_TEMPLATES = sum(len(defs) for defs in DEFAULT_TEMPLATES.values())


# ── catalogue invariant: each role's default_weights sum to exactly 100.00 ──
@pytest.mark.parametrize("role", list(DEFAULT_TEMPLATES))
def test_default_templates_weights_sum_to_100_per_role(role):
    total = sum(d["default_weight"] for d in DEFAULT_TEMPLATES[role])
    assert total == Decimal("100.00")


@pytest.mark.parametrize("role", list(DEFAULT_TEMPLATES))
def test_default_templates_have_2_to_4_kpis(role):
    assert 2 <= len(DEFAULT_TEMPLATES[role]) <= 4


# ── seeding: correct count, idempotent, tenant-scoped ───────────────────────
def test_seed_creates_expected_rows():
    t = TenantFactory()
    created = seed_templates_for_tenant(t)
    assert created == _TOTAL_TEMPLATES
    with tenant_context(t):
        assert KpiTemplate.objects.count() == _TOTAL_TEMPLATES


def test_seed_is_idempotent():
    t = TenantFactory()
    first = seed_templates_for_tenant(t)
    second = seed_templates_for_tenant(t)
    assert first == _TOTAL_TEMPLATES
    assert second == 0  # nothing new the second time
    with tenant_context(t):
        assert KpiTemplate.objects.count() == _TOTAL_TEMPLATES


def test_seed_is_tenant_scoped():
    a, b = TenantFactory(), TenantFactory()
    seed_templates_for_tenant(a)
    # Tenant b never seeded: its scoped manager sees nothing.
    with tenant_context(b):
        assert KpiTemplate.objects.count() == 0
    with tenant_context(a):
        assert KpiTemplate.objects.count() == _TOTAL_TEMPLATES


# ── instantiation: a Goal + the right KPIs, weight-complete, in tenant ──────
def test_instantiate_role_templates_builds_weight_complete_goal():
    t = TenantFactory()
    seed_templates_for_tenant(t)
    emp = UserFactory(tenant=t, role="MANAGER")
    cyc = CycleFactory(tenant=t)
    expected_kpis = len(DEFAULT_TEMPLATES["MANAGER"])

    goal = instantiate_role_templates(employee=emp, cycle=cyc, created_by=emp)

    with tenant_context(t):
        goal = Goal.objects.get(id=goal.id)
        assert goal.tenant_id == t.id
        assert goal.status == Goal.Status.DRAFT
        assert goal.created_by_id == emp.id
        assert goal.weight == Decimal("100.00")
        assert goal.kpis.count() == expected_kpis
        # The instantiated KPIs satisfy the "= 100.00" rule.
        assert assert_kpi_weights_complete(goal) == Decimal("100.00")
        for kpi in goal.kpis.all():
            assert kpi.tenant_id == t.id
            assert kpi.source == Kpi.Source.MANUAL


def test_instantiate_templates_with_explicit_set():
    t = TenantFactory()
    seed_templates_for_tenant(t)
    emp = UserFactory(tenant=t, role="EMPLOYEE")
    cyc = CycleFactory(tenant=t)
    with tenant_context(t):
        templates = list(KpiTemplate.objects.filter(role="EMPLOYEE"))

    goal = instantiate_templates(
        templates=templates,
        employee=emp,
        cycle=cyc,
        created_by=emp,
        goal_title="My objectives",
    )

    with tenant_context(t):
        goal = Goal.objects.get(id=goal.id)
        assert goal.title == "My objectives"
        assert goal.kpis.count() == len(templates)
        assert assert_kpi_weights_complete(goal) == Decimal("100.00")


# ── instantiation rejects weight-incomplete sets and rolls back ─────────────
def test_instantiate_rejects_non_100_and_rolls_back():
    t = TenantFactory()
    emp = UserFactory(tenant=t, role="EMPLOYEE")
    cyc = CycleFactory(tenant=t)
    # 50 + 40 = 90, not 100.
    templates = [
        KpiTemplateFactory(tenant=t, default_weight=Decimal("50.00")),
        KpiTemplateFactory(tenant=t, default_weight=Decimal("40.00")),
    ]

    with pytest.raises(ValidationError):
        instantiate_templates(
            templates=templates, employee=emp, cycle=cyc, created_by=emp
        )

    # Validation fires before any write, and the transaction rolls back: no rows.
    with tenant_context(t):
        assert Goal.objects.count() == 0
        assert Kpi.objects.count() == 0


# ── management command ──────────────────────────────────────────────────────
def test_seed_command_seeds_by_slug():
    t = TenantFactory(slug="acme")
    call_command("seed_kpi_templates", "--tenant-slug", t.slug)
    with tenant_context(t):
        assert KpiTemplate.objects.count() == _TOTAL_TEMPLATES


def test_seed_command_unknown_slug_errors():
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("seed_kpi_templates", "--tenant-slug", "does-not-exist")
