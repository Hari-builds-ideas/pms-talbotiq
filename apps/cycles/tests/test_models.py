import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.cycles.models import PerformanceCycle
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, TenantFactory

pytestmark = pytest.mark.django_db


def test_elapsed_fraction_is_clamped_and_exact():
    t = TenantFactory()
    cycle = CycleFactory(
        tenant=t, start_date=datetime.date(2026, 1, 1), end_date=datetime.date(2026, 1, 11)
    )
    assert cycle.elapsed_fraction(datetime.date(2025, 12, 31)) == Decimal("0")
    assert cycle.elapsed_fraction(datetime.date(2026, 1, 1)) == Decimal("0")
    assert cycle.elapsed_fraction(datetime.date(2026, 1, 6)) == Decimal("0.5000")
    assert cycle.elapsed_fraction(datetime.date(2026, 1, 11)) == Decimal("1")
    assert cycle.elapsed_fraction(datetime.date(2026, 2, 1)) == Decimal("1")


def test_clean_rejects_end_before_start():
    t = TenantFactory()
    cycle = PerformanceCycle(
        tenant=t, name="bad", start_date=datetime.date(2026, 3, 1), end_date=datetime.date(2026, 1, 1)
    )
    with pytest.raises(ValidationError):
        cycle.clean()


def test_cycle_cross_tenant_isolation():
    a, b = TenantFactory(), TenantFactory()
    cycle = CycleFactory(tenant=a)
    with tenant_context(b):
        assert PerformanceCycle.objects.filter(id=cycle.id).count() == 0
    with tenant_context(a):
        assert PerformanceCycle.objects.filter(id=cycle.id).count() == 1
