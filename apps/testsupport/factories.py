"""
Shared factory_boy factories. Importable from any app's tests:

    from apps.testsupport.factories import TenantFactory, UserFactory

Model references are lazy strings so importing this module never requires the
app registry to be ready. ``UserFactory`` routes through the custom
``create_user`` manager so passwords are Argon2-hashed exactly as in production.
"""
import datetime
from decimal import Decimal

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory


class TenantFactory(DjangoModelFactory):
    class Meta:
        model = "tenancy.Tenant"

    name = factory.Sequence(lambda n: f"Tenant {n}")
    slug = factory.Sequence(lambda n: f"tenant-{n}")
    status = "ACTIVE"


class UserFactory(DjangoModelFactory):
    class Meta:
        model = "identity.User"

    tenant = factory.SubFactory(TenantFactory)
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    role = "EMPLOYEE"
    is_active = True
    mfa_enabled = False
    password = "pass12345!"

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop("password", None)
        manager = model_class._default_manager
        return manager.create_user(*args, password=password, **kwargs)


class ScopedThingFactory(DjangoModelFactory):
    class Meta:
        model = "testsupport.ScopedThing"

    # tenant is intentionally NOT a SubFactory: callers pass it explicitly so
    # cross-tenant tests stay unambiguous about which tenant owns each row.
    name = factory.Sequence(lambda n: f"thing-{n}")


# ── Module 2 — Goals & KPI engine ──────────────────────────────────────────
# For the goal tree, tenant is DERIVED from the parent (employee/goal/kpi) via
# SelfAttribute so the whole graph stays in one tenant — passing independent
# SubFactories would create cross-tenant rows that the write-isolation save()
# rejects. Callers pass the parent objects explicitly.


class CycleFactory(DjangoModelFactory):
    class Meta:
        model = "cycles.PerformanceCycle"

    tenant = factory.SubFactory(TenantFactory)
    name = factory.Sequence(lambda n: f"Cycle {n}")
    start_date = datetime.date(2026, 1, 1)
    end_date = datetime.date(2026, 3, 31)
    status = "ACTIVE"


class GoalFactory(DjangoModelFactory):
    class Meta:
        model = "goals.Goal"

    # Pass employee= and cycle= (same tenant); tenant is derived from employee.
    tenant = factory.SelfAttribute("employee.tenant")
    created_by = factory.SelfAttribute("employee")
    title = factory.Sequence(lambda n: f"Goal {n}")
    weight = Decimal("100.00")
    status = "ACTIVE"


class KpiFactory(DjangoModelFactory):
    class Meta:
        model = "goals.Kpi"

    # Pass goal=; tenant is derived from the goal.
    tenant = factory.SelfAttribute("goal.tenant")
    name = factory.Sequence(lambda n: f"KPI {n}")
    weight = Decimal("100.00")
    target_value = Decimal("100.0000")
    direction = "INCREASING"
    unit = ""
    source = "MANUAL"


class KpiMeasurementFactory(DjangoModelFactory):
    class Meta:
        model = "goals.KpiMeasurement"

    # Pass kpi=; tenant is derived from the kpi.
    tenant = factory.SelfAttribute("kpi.tenant")
    value = Decimal("100.0000")
    recorded_at = factory.LazyFunction(timezone.now)
    source = "MANUAL"


class KpiTemplateFactory(DjangoModelFactory):
    class Meta:
        model = "goals.KpiTemplate"

    tenant = factory.SubFactory(TenantFactory)
    role = "EMPLOYEE"
    name = factory.Sequence(lambda n: f"Template KPI {n}")
    target_value = Decimal("100.0000")
    direction = "INCREASING"
    unit = ""
    default_weight = Decimal("100.00")
