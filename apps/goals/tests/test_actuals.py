"""
Tests for the single actuals write path, :func:`apps.goals.services.record_actual`.

Covers: append-only history (latest by recorded_at is current), exact-Decimal
storage, system/now defaults, and tenant isolation of the written measurement.
"""
import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.goals.models import KpiMeasurement
from apps.goals.services import record_actual
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import (
    CycleFactory,
    GoalFactory,
    KpiFactory,
    TenantFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def _make_kpi(tenant):
    goal = GoalFactory(employee=UserFactory(tenant=tenant), cycle=CycleFactory(tenant=tenant))
    return KpiFactory(goal=goal)


def test_record_actual_creates_measurement_with_expected_fields():
    t = TenantFactory()
    kpi = _make_kpi(t)
    recorder = UserFactory(tenant=t)
    when = timezone.now()

    m = record_actual(
        kpi,
        Decimal("42.0000"),
        source=KpiMeasurement.Source.JIRA,
        recorded_at=when,
        recorded_by=recorder,
    )

    assert m.kpi_id == kpi.id
    assert m.tenant_id == kpi.tenant_id
    assert m.value == Decimal("42.0000")
    assert m.source == KpiMeasurement.Source.JIRA
    assert m.recorded_by_id == recorder.id
    assert m.recorded_at == when


def test_record_actual_appends_history_latest_by_recorded_at_is_current():
    t = TenantFactory()
    kpi = _make_kpi(t)
    base = timezone.now()

    # Write three out of chronological insertion order to prove "latest" is by
    # recorded_at, not by insertion time, and that all three persist (append).
    record_actual(kpi, Decimal("10.0000"), recorded_at=base)
    newest = record_actual(kpi, Decimal("30.0000"), recorded_at=base + datetime.timedelta(hours=2))
    record_actual(kpi, Decimal("20.0000"), recorded_at=base + datetime.timedelta(hours=1))

    with tenant_context(t):
        qs = KpiMeasurement.objects.filter(kpi=kpi)
        assert qs.count() == 3  # all three persist — no row was mutated
        # Default ordering is -recorded_at, so first() is the current actual.
        current = qs.first()
        assert current.id == newest.id
        assert current.value == Decimal("30.0000")


def test_record_actual_stores_decimal_exactly_no_float_drift():
    t = TenantFactory()
    kpi = _make_kpi(t)

    m = record_actual(kpi, Decimal("33.3333"))

    with tenant_context(t):
        reread = KpiMeasurement.objects.get(id=m.id)
    assert reread.value == Decimal("33.3333")


def test_record_actual_defaults_recorded_by_none_and_recorded_at_now():
    t = TenantFactory()
    kpi = _make_kpi(t)
    before = timezone.now()

    m = record_actual(kpi, Decimal("5.0000"))

    after = timezone.now()
    assert m.recorded_by_id is None  # system measurement
    assert m.source == KpiMeasurement.Source.MANUAL  # default source
    assert before <= m.recorded_at <= after  # defaulted to ~now


def test_record_actual_measurement_is_tenant_isolated():
    a, b = TenantFactory(), TenantFactory()
    kpi = _make_kpi(a)

    m = record_actual(kpi, Decimal("7.0000"))

    with tenant_context(b):
        assert KpiMeasurement.objects.filter(id=m.id).count() == 0
    with tenant_context(a):
        assert KpiMeasurement.objects.filter(id=m.id).count() == 1
