from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.goals.models import Goal, Kpi
from apps.goals.validators import (
    assert_active_goal_weights_complete,
    assert_kpi_weights_complete,
    assert_weights_sum_to_100,
    validate_target_value,
)
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import (
    CycleFactory,
    GoalFactory,
    KpiFactory,
    TenantFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


# ── the "= 100.00" rule: exact Decimal equality, both boundaries ───────────
@pytest.mark.parametrize(
    "weights",
    [["100.00"], ["50.00", "50.00"], ["33.33", "33.33", "33.34"], ["0.00", "100.00"]],
)
def test_weights_summing_to_100_accepted(weights):
    assert assert_weights_sum_to_100([Decimal(w) for w in weights]) == Decimal("100.00")


@pytest.mark.parametrize(
    "weights",
    [["99.99"], ["100.01"], ["50.00", "49.99"], ["50.00", "50.02"], ["33.33", "33.33", "33.33"], []],
)
def test_weights_not_summing_to_100_rejected(weights):
    with pytest.raises(ValidationError):
        assert_weights_sum_to_100([Decimal(w) for w in weights])


# ── KPI-weights-per-goal (level 1) ─────────────────────────────────────────
def test_goal_kpi_weights_complete_accepted():
    t = TenantFactory()
    goal = GoalFactory(employee=UserFactory(tenant=t), cycle=CycleFactory(tenant=t))
    KpiFactory(goal=goal, weight=Decimal("60.00"))
    KpiFactory(goal=goal, weight=Decimal("40.00"))
    with tenant_context(t):
        assert assert_kpi_weights_complete(goal) == Decimal("100.00")


def test_goal_kpi_weights_9999_rejected():
    t = TenantFactory()
    goal = GoalFactory(employee=UserFactory(tenant=t), cycle=CycleFactory(tenant=t))
    KpiFactory(goal=goal, weight=Decimal("60.00"))
    KpiFactory(goal=goal, weight=Decimal("39.99"))  # 99.99
    with tenant_context(t), pytest.raises(ValidationError):
        assert_kpi_weights_complete(goal)


# ── ACTIVE-goal-weights-per-employee-cycle (level 2) ───────────────────────
def test_active_goal_weights_complete_accepted():
    t = TenantFactory()
    emp, cyc = UserFactory(tenant=t), CycleFactory(tenant=t)
    GoalFactory(employee=emp, cycle=cyc, weight=Decimal("70.00"), status="ACTIVE")
    GoalFactory(employee=emp, cycle=cyc, weight=Decimal("30.00"), status="ACTIVE")
    with tenant_context(t):
        assert assert_active_goal_weights_complete(emp, cyc) == Decimal("100.00")


def test_active_goal_weights_10001_rejected():
    t = TenantFactory()
    emp, cyc = UserFactory(tenant=t), CycleFactory(tenant=t)
    GoalFactory(employee=emp, cycle=cyc, weight=Decimal("70.00"), status="ACTIVE")
    GoalFactory(employee=emp, cycle=cyc, weight=Decimal("30.01"), status="ACTIVE")  # 100.01
    with tenant_context(t), pytest.raises(ValidationError):
        assert_active_goal_weights_complete(emp, cyc)


def test_active_goal_weights_ignore_non_active():
    t = TenantFactory()
    emp, cyc = UserFactory(tenant=t), CycleFactory(tenant=t)
    GoalFactory(employee=emp, cycle=cyc, weight=Decimal("100.00"), status="ACTIVE")
    GoalFactory(employee=emp, cycle=cyc, weight=Decimal("50.00"), status="DRAFT")  # ignored
    with tenant_context(t):
        assert assert_active_goal_weights_complete(emp, cyc) == Decimal("100.00")


# ── target_value > 0 ───────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", ["0", "-1", "-0.0001"])
def test_target_value_must_be_positive(bad):
    with pytest.raises(ValidationError):
        validate_target_value(Decimal(bad))


def test_target_value_positive_ok():
    validate_target_value(Decimal("0.0001"))  # does not raise


# ── tenant isolation on the new models ─────────────────────────────────────
def test_goal_kpi_cross_tenant_reads_impossible():
    a, b = TenantFactory(), TenantFactory()
    goal = GoalFactory(employee=UserFactory(tenant=a), cycle=CycleFactory(tenant=a))
    kpi = KpiFactory(goal=goal)
    with tenant_context(b):
        assert Goal.objects.filter(id=goal.id).count() == 0
        assert Kpi.objects.filter(id=kpi.id).count() == 0
    with tenant_context(a):
        assert Goal.objects.filter(id=goal.id).count() == 1
        assert Kpi.objects.filter(id=kpi.id).count() == 1


def test_cross_tenant_goal_write_blocked():
    a, b = TenantFactory(), TenantFactory()
    emp_b, cyc_b = UserFactory(tenant=b), CycleFactory(tenant=b)
    with tenant_context(a), pytest.raises(PermissionError):
        Goal.objects.create(
            tenant=b, employee=emp_b, cycle=cyc_b, title="x", weight=Decimal("100.00")
        )
