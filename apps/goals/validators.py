"""
Weight validation — the "= 100%" rule, applied at two levels with EXACT Decimal
equality (no float, no tolerance):

* a Goal's KPIs' weights must sum to exactly 100.00;
* an employee's ACTIVE Goals' weights within a cycle must sum to exactly 100.00.

These power the editor's live-sum indicator and are enforced server-side by the
serializers. The query-based helpers read scoped managers, so they must run with
a tenant bound (always true on a request; use ``tenant_context`` in tests).
"""
from decimal import Decimal

from django.core.exceptions import ValidationError

REQUIRED_WEIGHT_TOTAL = Decimal("100.00")


def assert_weights_sum_to_100(weights, label="Weight"):
    """Raise ValidationError unless ``weights`` sum to EXACTLY 100.00.

    ``weights`` is any iterable of Decimal-coercible values. 99.99 and 100.01 are
    both rejected; 100.00 is accepted. Returns the total on success.
    """
    total = sum((Decimal(str(w)) for w in weights), Decimal("0"))
    if total != REQUIRED_WEIGHT_TOTAL:
        raise ValidationError(
            f"{label} weights must sum to exactly 100.00 (got {total})."
        )
    return total


def assert_kpi_weights_complete(goal):
    """A goal's KPIs must weigh exactly 100.00 in total."""
    return assert_weights_sum_to_100(
        [k.weight for k in goal.kpis.all()], label="A goal's KPI"
    )


def assert_active_goal_weights_complete(employee, cycle):
    """An employee's ACTIVE goals in a cycle must weigh exactly 100.00 in total.

    Accepts User/PerformanceCycle instances or their ids.
    """
    from .models import Goal  # local import: avoids a model import at module load

    employee_id = getattr(employee, "id", employee)
    cycle_id = getattr(cycle, "id", cycle)
    weights = Goal.objects.filter(
        employee_id=employee_id, cycle_id=cycle_id, status=Goal.Status.ACTIVE
    ).values_list("weight", flat=True)
    return assert_weights_sum_to_100(list(weights), label="An employee's active goal")


def validate_target_value(value):
    """KPI target_value must be strictly greater than 0."""
    if value is None or Decimal(str(value)) <= 0:
        raise ValidationError("target_value must be greater than 0.")
