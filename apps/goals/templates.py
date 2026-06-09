"""
Role-targeted KPI templates: a deterministic per-role catalogue, idempotent
per-tenant seeding, and instantiation into real Goal/KPI rows.

Deterministic only — the AI template-suggestion path is Phase 2 (out of scope).

CRITICAL invariant: for EACH role, the template ``default_weight``s sum to
EXACTLY 100.00, so instantiating a role's whole set yields a Goal whose KPIs are
weight-complete (the "= 100.00" rule, enforced with exact Decimal equality by
:func:`apps.goals.validators.assert_weights_sum_to_100`). All weights/targets are
``Decimal`` literals — never float — so seeding is exactly reproducible.

Rows are created under ``tenant_context(tenant)`` so this works inside a request
(tenant already bound) or from system code such as the seed management command
(no request); ``TenantScopedModel.save`` then stamps the bound tenant.
"""
from decimal import Decimal

from django.db import transaction

from apps.identity.models import User
from apps.tenancy.context import tenant_context

from .models import Goal, Kpi, KpiTemplate
from .validators import assert_weights_sum_to_100

# Per-role default catalogue. Each role's default_weights sum to EXACTLY 100.00.
DEFAULT_TEMPLATES = {
    User.Role.EMPLOYEE: [
        {
            "name": "Deliverables completed on time",
            "description": "Share of assigned deliverables shipped by their due date.",
            "target_value": Decimal("95.0000"),
            "direction": KpiTemplate.Direction.INCREASING,
            "unit": "%",
            "default_weight": Decimal("40.00"),
        },
        {
            "name": "Quality / defect rate",
            "description": "Defects or rework raised against the employee's output.",
            "target_value": Decimal("2.0000"),
            "direction": KpiTemplate.Direction.DECREASING,
            "unit": "defects",
            "default_weight": Decimal("35.00"),
        },
        {
            "name": "Skill development hours",
            "description": "Hours invested in role-relevant learning this cycle.",
            "target_value": Decimal("20.0000"),
            "direction": KpiTemplate.Direction.INCREASING,
            "unit": "hours",
            "default_weight": Decimal("25.00"),
        },
    ],
    User.Role.MANAGER: [
        {
            "name": "Team goal attainment",
            "description": "Average cycle-score attainment across direct reports.",
            "target_value": Decimal("90.0000"),
            "direction": KpiTemplate.Direction.INCREASING,
            "unit": "%",
            "default_weight": Decimal("40.00"),
        },
        {
            "name": "Reviews completed on time",
            "description": "Share of direct-report reviews submitted by the deadline.",
            "target_value": Decimal("100.0000"),
            "direction": KpiTemplate.Direction.INCREASING,
            "unit": "%",
            "default_weight": Decimal("30.00"),
        },
        {
            "name": "Voluntary regrettable attrition",
            "description": "Regrettable voluntary departures from the team this cycle.",
            "target_value": Decimal("1.0000"),
            "direction": KpiTemplate.Direction.DECREASING,
            "unit": "people",
            "default_weight": Decimal("30.00"),
        },
    ],
    User.Role.HRBP: [
        {
            "name": "Cycle completion across business unit",
            "description": "Share of employees in the BU with a completed cycle.",
            "target_value": Decimal("98.0000"),
            "direction": KpiTemplate.Direction.INCREASING,
            "unit": "%",
            "default_weight": Decimal("35.00"),
        },
        {
            "name": "Time to close open requisitions",
            "description": "Average days to fill an open role in the business unit.",
            "target_value": Decimal("30.0000"),
            "direction": KpiTemplate.Direction.DECREASING,
            "unit": "days",
            "default_weight": Decimal("35.00"),
        },
        {
            "name": "Engagement survey participation",
            "description": "Share of BU employees responding to the engagement survey.",
            "target_value": Decimal("85.0000"),
            "direction": KpiTemplate.Direction.INCREASING,
            "unit": "%",
            "default_weight": Decimal("30.00"),
        },
    ],
    User.Role.ADMIN: [
        {
            "name": "Platform availability (uptime)",
            "description": "Tenant-facing uptime of the PMS platform this cycle.",
            "target_value": Decimal("99.9000"),
            "direction": KpiTemplate.Direction.INCREASING,
            "unit": "%",
            "default_weight": Decimal("50.00"),
        },
        {
            "name": "Open security findings",
            "description": "Unresolved security findings at cycle end.",
            "target_value": Decimal("0.0000"),
            "direction": KpiTemplate.Direction.DECREASING,
            "unit": "findings",
            "default_weight": Decimal("50.00"),
        },
    ],
}


def seed_templates_for_tenant(tenant) -> int:
    """Idempotently create :class:`KpiTemplate` rows for ``tenant`` from
    :data:`DEFAULT_TEMPLATES`; return the number of rows created.

    Skips any template that already exists for ``(tenant, role, name)`` so running
    the seed repeatedly never produces duplicates. Runs under
    ``tenant_context(tenant)`` so it works from system code with no bound request;
    ``TenantScopedModel.save`` stamps the bound tenant on each new row.
    """
    created = 0
    with tenant_context(tenant), transaction.atomic():
        for role, definitions in DEFAULT_TEMPLATES.items():
            for definition in definitions:
                _, was_created = KpiTemplate.objects.get_or_create(
                    role=str(role),
                    name=definition["name"],
                    defaults={
                        "description": definition["description"],
                        "target_value": definition["target_value"],
                        "direction": definition["direction"],
                        "unit": definition["unit"],
                        "default_weight": definition["default_weight"],
                    },
                )
                if was_created:
                    created += 1
    return created


@transaction.atomic
def instantiate_templates(
    *,
    templates,
    employee,
    cycle,
    created_by,
    goal_title=None,
    goal_weight=Decimal("100.00"),
) -> Goal:
    """Instantiate ``templates`` into ONE Goal plus one Kpi per template, in the
    employee's tenant, and return the created Goal.

    The chosen templates' ``default_weight``s are validated to sum to EXACTLY
    100.00 BEFORE any row is written, so the resulting goal is always
    weight-valid. Everything happens in one transaction: if validation fails,
    nothing is created. The Goal is created as DRAFT; each Kpi copies the
    template's name/target_value/direction/unit, takes the template's
    ``default_weight``, and is sourced MANUAL.
    """
    templates = list(templates)
    # Fail before any write: the goal's KPIs must sum to exactly 100.00.
    assert_weights_sum_to_100([t.default_weight for t in templates], "Template KPI")

    tenant_id = employee.tenant_id
    goal = Goal.objects.create(
        tenant_id=tenant_id,
        employee=employee,
        created_by=created_by,
        cycle=cycle,
        title=goal_title or f"{employee.role} goals",
        weight=goal_weight,
        status=Goal.Status.DRAFT,
    )
    for template in templates:
        Kpi.objects.create(
            tenant_id=tenant_id,
            goal=goal,
            name=template.name,
            target_value=template.target_value,
            direction=template.direction,
            unit=template.unit,
            weight=template.default_weight,
            source=Kpi.Source.MANUAL,
        )
    return goal


def instantiate_role_templates(*, employee, cycle, created_by, role=None) -> Goal:
    """Convenience wrapper: load the tenant's :class:`KpiTemplate` rows for
    ``role`` (defaulting to the employee's role) and instantiate them into a Goal.

    Reads the scoped ``KpiTemplate`` manager under the employee's tenant, so the
    templates are exactly the ones seeded for that tenant.
    """
    role = role or employee.role
    with tenant_context(employee.tenant_id):
        templates = list(KpiTemplate.objects.filter(role=str(role)))
    return instantiate_templates(
        templates=templates,
        employee=employee,
        cycle=cycle,
        created_by=created_by,
    )
