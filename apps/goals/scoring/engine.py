"""
The DETERMINISTIC T/Z scoring engine — the correctness core of Module 2.

Fully reproducible: ``Decimal`` arithmetic throughout, NO randomness, NO AI, NO
network. Given the same rows it always returns the same numbers, bit-for-bit.

The pipeline, per (tenant, cycle):

    KPI actual ──> kpi_attainment   (actual vs target, clamped to [floor, cap])
        └─ Σ weighted ──> goal_raw_score
            └─ Σ weighted ──> employee_raw_score
                └─ across the cohort ──> population_mean_std ──> normalize (Z, T)
                    └─ risk_status (+ pace_behind)
                        └─ idempotent CycleScore upsert ──> cycle_scores_recomputed

Rounding policy: intermediate results are quantized to ``INTERNAL_DP`` (4 dp).
Display rounding (2 dp) is a presentation concern and is NOT applied here — the
stored CycleScore fields keep the 4-dp internal precision.

Tenant binding: this engine runs OFF the request path (Celery), where no tenant is
bound and the scoped managers FAIL CLOSED. So ``compute_cycle_scores`` binds the
tenant itself via ``with tenant_context(tenant_id):`` around all ORM access. The
pure math helpers below are tenant-agnostic and take already-loaded values/objects.
"""
from decimal import Decimal, getcontext

from django.utils import timezone

from apps.cycles.models import PerformanceCycle
from apps.tenancy.context import tenant_context

from ..models import CycleScore, Goal, KpiMeasurement
from ..signals import cycle_scores_recomputed
from .constants import (
    ABS_AT_RISK,
    ABS_CRITICAL,
    ATTAINMENT_CAP,
    ATTAINMENT_FLOOR,
    INTERNAL_DP,
    PACE_SHORTFALL,
    T_AT_RISK,
    T_CRITICAL,
)

# A generous Decimal precision so Decimal.sqrt() in population_mean_std is exact to
# well beyond our 4-dp output granularity (28 is the default; we lift it to be safe
# for large cohorts / wide value ranges). Set at import; the engine never mutates it
# per-call, so behaviour stays deterministic.
getcontext().prec = 50


def _q(value) -> Decimal:
    """Quantize an internal intermediate result to 4 dp (``INTERNAL_DP``)."""
    return Decimal(value).quantize(INTERNAL_DP)


def kpi_attainment(kpi) -> Decimal:
    """Attainment of a single KPI: how close the latest actual is to target.

    The "actual" is the value of the latest :class:`KpiMeasurement` for this KPI,
    ordered by ``recorded_at`` desc then ``created_at`` desc. With NO measurement
    the KPI scores 0 (nothing delivered yet).

    INCREASING (higher is better):  actual / target
    DECREASING (lower is better):   target / actual; actual == 0 means a perfect
                                    "drove it to zero" result, credited at the cap.

    The ratio is clamped to ``[ATTAINMENT_FLOOR, ATTAINMENT_CAP]``. ``target_value``
    is guaranteed > 0 by validation, so the INCREASING path never divides by zero.
    Result is quantized to 4 dp.
    """
    latest = (
        KpiMeasurement.objects.filter(kpi_id=kpi.id)
        .order_by("-recorded_at", "-created_at")
        .first()
    )
    if latest is None:
        return _q(ATTAINMENT_FLOOR)

    actual = latest.value
    target = kpi.target_value

    if kpi.direction == kpi.Direction.DECREASING:
        if actual == 0:
            # Drove the metric to zero — the best possible result; credit at cap.
            attainment = ATTAINMENT_CAP
        else:
            attainment = target / actual
    else:  # INCREASING (default)
        attainment = actual / target

    # Clamp to [floor, cap].
    if attainment < ATTAINMENT_FLOOR:
        attainment = ATTAINMENT_FLOOR
    elif attainment > ATTAINMENT_CAP:
        attainment = ATTAINMENT_CAP
    return _q(attainment)


def goal_raw_score(goal) -> Decimal:
    """A goal's raw score: weight-share-blended attainment of its KPIs.

    Σ over the goal's KPIs of ``(kpi.weight / 100) * kpi_attainment(kpi)``. A goal
    with no KPIs scores 0. Result quantized to 4 dp.
    """
    total = Decimal("0")
    for kpi in goal.kpis.all():
        contribution = (kpi.weight / Decimal("100")) * kpi_attainment(kpi)
        total += _q(contribution)
    return _q(total)


def employee_raw_score(employee_id, cycle_id) -> Decimal:
    """An employee's raw score for a cycle: weight-blended over their ACTIVE goals.

    Σ over the employee's ACTIVE goals in the cycle of
    ``(goal.weight / 100) * goal_raw_score(goal)``. No active goals -> 0. Result
    quantized to 4 dp. (Caller must already be inside ``tenant_context``.)
    """
    total = Decimal("0")
    goals = Goal.objects.filter(
        employee_id=employee_id, cycle_id=cycle_id, status=Goal.Status.ACTIVE
    )
    for goal in goals:
        contribution = (goal.weight / Decimal("100")) * goal_raw_score(goal)
        total += _q(contribution)
    return _q(total)


def population_mean_std(values):
    """Population mean and standard deviation of ``values``, Decimal-exact.

    mean = Σx / n
    std  = sqrt( Σ(x - mean)² / n )   (POPULATION σ, divisor n — not n-1)

    Uses ``Decimal.sqrt`` under the wide module precision set above, so there is no
    float drift. Returns ``(mean, std)`` both quantized to 4 dp. Empty input is
    treated as ``(0, 0)`` (the orchestrator never calls it empty).
    """
    n = len(values)
    if n == 0:
        return _q(Decimal("0")), _q(Decimal("0"))

    total = sum(values, Decimal("0"))
    mean = total / Decimal(n)

    variance = sum(((x - mean) ** 2 for x in values), Decimal("0")) / Decimal(n)
    std = variance.sqrt()
    return _q(mean), _q(std)


def normalize(raw, mean, std):
    """Normalize a raw score against its cohort into Z- and T-scores.

    Returns ``(z, t, insufficient)``.

    A Z/T is only meaningful with a real cohort and real spread, so when the cohort
    has fewer than 2 members OR zero spread (std == 0) we return z=0, t=50 and flag
    ``insufficient=True`` (the caller then uses the absolute-raw risk fallback).
    Otherwise z = (raw - mean) / std, and t = 50 + 10*z clamped to [0, 100]. Both
    z and t are quantized to 4 dp.
    """
    # n is implied by the caller; std==0 also covers the n<2 case (a single value
    # has std 0), but the orchestrator passes n explicitly via the cohort size and
    # sets insufficient there too — here we guard on std to stay self-contained.
    if std == 0:
        return _q(Decimal("0")), _q(Decimal("50")), True

    # Quantize z to the 4-dp internal precision FIRST, then derive t from that same
    # rounded z, so the stored z and t are mutually consistent (t == 50 + 10*z at
    # 4 dp). Computing t from a higher-precision z than the one we store would make
    # the pair disagree at the 4th decimal.
    z = _q((raw - mean) / std)
    t = Decimal("50") + Decimal("10") * z
    if t < Decimal("0"):
        t = Decimal("0")
    elif t > Decimal("100"):
        t = Decimal("100")
    return z, _q(t), False


def risk_status(t, raw, insufficient) -> str:
    """Map (T-score, raw, insufficient) to a :class:`CycleScore.Risk` value.

    Cohort path (insufficient is False) — tiers on the normalized T-score:
        t < T_CRITICAL              -> CRITICAL
        T_CRITICAL <= t < T_AT_RISK -> AT_RISK
        else                        -> ON_TRACK

    Fallback path (insufficient is True) — tiers on the ABSOLUTE raw score:
        raw < ABS_CRITICAL              -> CRITICAL
        ABS_CRITICAL <= raw < ABS_AT_RISK -> AT_RISK
        else                            -> ON_TRACK
    """
    if not insufficient:
        if t < T_CRITICAL:
            return CycleScore.Risk.CRITICAL
        if t < T_AT_RISK:
            return CycleScore.Risk.AT_RISK
        return CycleScore.Risk.ON_TRACK

    if raw < ABS_CRITICAL:
        return CycleScore.Risk.CRITICAL
    if raw < ABS_AT_RISK:
        return CycleScore.Risk.AT_RISK
    return CycleScore.Risk.ON_TRACK


def pace_behind(cycle, raw, as_of=None) -> bool:
    """Whether an employee is behind the expected delivery pace for the cycle.

    True iff the cycle is ACTIVE and ``raw < cycle.elapsed_fraction(as_of) *
    PACE_SHORTFALL``. This is a SEPARATE signal from the risk tier — it does NOT
    feed ``risk_status`` (a strong performer can be coasting; a weak one can be
    front-loaded). Closed/draft cycles are never "behind pace".
    """
    if not cycle.is_active:
        return False
    threshold = cycle.elapsed_fraction(as_of) * PACE_SHORTFALL
    return raw < threshold


def compute_cycle_scores(tenant_id, cycle_id, as_of=None):
    """Recompute and idempotently store every employee's CycleScore for a cycle.

    The orchestrator. Runs off the request path, so it binds the tenant itself.

    1. Cohort = employees with >=1 ACTIVE Goal in this (tenant, cycle).
    2. Each employee's raw score (may be 0 — they still count toward the cohort).
    3. Cohort mean/std over the raw scores; per-employee z/t/insufficient/risk/pace.
       The cohort is "insufficient" when n < 2 OR std == 0 (no meaningful spread),
       in which case risk uses the absolute-raw fallback.
    4. Idempotent ``update_or_create`` of one CycleScore per employee (unique per
       tenant+employee+cycle): re-running yields identical score fields and NO
       duplicate rows — only ``computed_at`` changes.
    5. AFTER storing, fire ``cycle_scores_recomputed`` with the structured risk
       data for the Agent-2 nudge layer (Module 10). This engine composes/sends
       nothing else.

    Returns the list of stored CycleScore rows.
    """
    with tenant_context(tenant_id):
        # 1. Cohort: distinct employee ids that own an ACTIVE goal in this cycle.
        employee_ids = list(
            Goal.objects.filter(cycle_id=cycle_id, status=Goal.Status.ACTIVE)
            .values_list("employee_id", flat=True)
            .distinct()
        )
        # Deterministic ordering so the cohort list / signal payload is stable.
        employee_ids = sorted(employee_ids, key=str)

        # 2. Raw score per employee.
        raws = {eid: employee_raw_score(eid, cycle_id) for eid in employee_ids}
        n = len(employee_ids)

        # 3. Cohort statistics + per-employee normalization.
        mean, std = population_mean_std(list(raws.values()))
        cohort_insufficient = n < 2 or std == 0

        # Need the cycle once for the pace check (tenant is bound).
        cycle = PerformanceCycle.objects.get(id=cycle_id)

        results = []
        for eid in employee_ids:
            raw = raws[eid]
            z, t, norm_insufficient = normalize(raw, mean, std)
            # Cohort is insufficient if EITHER n<2 OR normalize found no spread.
            insufficient = cohort_insufficient or norm_insufficient
            risk = risk_status(t, raw, insufficient)
            behind = pace_behind(cycle, raw, as_of)
            results.append(
                {
                    "employee_id": eid,
                    "raw_score": raw,
                    "z_score": z,
                    "t_score": t,
                    "insufficient_cohort": insufficient,
                    "risk_status": risk,
                    "pace_behind": behind,
                    "cohort_size": n,
                }
            )

        # 4. Idempotent upsert (one row per employee; unique tenant+emp+cycle).
        now = timezone.now()
        rows = []
        for r in results:
            score, _created = CycleScore.objects.update_or_create(
                employee_id=r["employee_id"],
                cycle_id=cycle_id,
                defaults={
                    "raw_score": r["raw_score"],
                    "z_score": r["z_score"],
                    "t_score": r["t_score"],
                    "cohort_size": n,
                    "cohort_key": "tenant",
                    "insufficient_cohort": r["insufficient_cohort"],
                    "risk_status": r["risk_status"],
                    "pace_behind": r["pace_behind"],
                    "computed_at": now,
                },
            )
            rows.append(score)

    # 5. Fire the Agent-2 trigger seam AFTER storing. Sent outside tenant_context
    #    is fine — the payload carries plain str ids, receivers bind their own.
    cycle_scores_recomputed.send(
        sender=compute_cycle_scores,
        tenant_id=str(tenant_id),
        cycle_id=str(cycle_id),
        scores=[
            {
                "employee_id": r["employee_id"],
                "raw_score": r["raw_score"],
                "z_score": r["z_score"],
                "t_score": r["t_score"],
                "risk_status": r["risk_status"],
                "pace_behind": r["pace_behind"],
                "insufficient_cohort": r["insufficient_cohort"],
                "cohort_size": r["cohort_size"],
            }
            for r in results
        ],
    )

    return rows
