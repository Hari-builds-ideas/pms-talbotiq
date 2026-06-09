"""
Exhaustive tests for the DETERMINISTIC T/Z scoring engine.

These tests LOCK the math: the golden example computes raw/z/t/risk by hand (the
arithmetic is shown in comments) and asserts the engine returns EXACTLY those
Decimals. They also pin the edge cases (no spread, tiny cohort, no measurement,
DECREASING direction, attainment clamp, pace, idempotency, Decimal exactness,
tenant isolation of the cohort, and the Agent-2 signal seam).

All ORM reads run inside ``tenant_context`` because the scoped managers fail closed.
"""
from decimal import Decimal

import datetime

import pytest
from django.utils import timezone

from apps.goals.models import CycleScore, Goal, Kpi
from apps.goals.scoring import constants as C
from apps.goals.scoring.engine import (
    compute_cycle_scores,
    employee_raw_score,
    goal_raw_score,
    kpi_attainment,
    normalize,
    pace_behind,
    population_mean_std,
    risk_status,
)
from apps.goals.signals import cycle_scores_recomputed
from apps.goals.tasks import recompute_cycle_scores
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import (
    CycleFactory,
    GoalFactory,
    KpiFactory,
    KpiMeasurementFactory,
    TenantFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


# ── helpers ─────────────────────────────────────────────────────────────────
def _simple_employee(tenant, cycle, measurement_value, *, direction="INCREASING",
                     target="100.0000", recorded_at=None):
    """One employee with one ACTIVE goal (w=100) holding one KPI (w=100).

    With a single 100%-weighted goal and a single 100%-weighted KPI, the employee's
    raw score equals that KPI's attainment — which keeps the golden arithmetic
    trivial to verify by hand. ``measurement_value=None`` means no measurement.
    Returns the employee.
    """
    emp = UserFactory(tenant=tenant)
    goal = GoalFactory(employee=emp, cycle=cycle, weight=Decimal("100.00"), status="ACTIVE")
    kpi = KpiFactory(
        goal=goal, weight=Decimal("100.00"), target_value=Decimal(target), direction=direction
    )
    if measurement_value is not None:
        KpiMeasurementFactory(
            kpi=kpi,
            value=Decimal(measurement_value),
            recorded_at=recorded_at or timezone.now(),
        )
    return emp


def _score_for(tenant, cycle, employee):
    with tenant_context(tenant):
        return CycleScore.objects.get(employee_id=employee.id, cycle_id=cycle.id)


# ── GOLDEN worked example: lock the math ────────────────────────────────────
def test_golden_worked_example():
    """Three employees, one tenant+cycle, distinct raws => real spread (sigma>0).

    Each employee: 1 goal (w=100) x 1 KPI (w=100, INCREASING, target=100). So
    raw == attainment == value/100:

        A: value 90 -> attainment 0.9000 -> raw 0.9000
        B: value 60 -> attainment 0.6000 -> raw 0.6000
        C: value 30 -> attainment 0.3000 -> raw 0.3000

        mean = (0.9 + 0.6 + 0.3) / 3 = 1.8 / 3 = 0.6000
        var  = ((0.9-0.6)^2 + 0 + (0.3-0.6)^2) / 3 = (0.09 + 0 + 0.09)/3 = 0.06
        std  = sqrt(0.06) = 0.244948974...  -> 0.2449 (4dp)

        z = (raw - 0.6) / 0.2449,  t = 50 + 10*z (clamped 0..100):
        A: z = 0.3 / 0.2449   =  1.2250 -> t = 62.2500 -> ON_TRACK (t >= 40)
        B: z = 0   / 0.2449   =  0.0000 -> t = 50.0000 -> ON_TRACK
        C: z = -0.3 / 0.2449  = -1.2250 -> t = 37.7500 -> AT_RISK  (30 <= t < 40)
    """
    t = TenantFactory()
    cyc = CycleFactory(tenant=t)
    a = _simple_employee(t, cyc, "90.0000")
    b = _simple_employee(t, cyc, "60.0000")
    c = _simple_employee(t, cyc, "30.0000")

    compute_cycle_scores(t.id, cyc.id)

    sa, sb, sc = _score_for(t, cyc, a), _score_for(t, cyc, b), _score_for(t, cyc, c)

    # cohort metadata
    for s in (sa, sb, sc):
        assert s.cohort_size == 3
        assert s.cohort_key == "tenant"
        assert s.insufficient_cohort is False

    # A
    assert sa.raw_score == Decimal("0.9000")
    assert sa.z_score == Decimal("1.2250")
    assert sa.t_score == Decimal("62.2500")
    assert sa.risk_status == CycleScore.Risk.ON_TRACK
    # B
    assert sb.raw_score == Decimal("0.6000")
    assert sb.z_score == Decimal("0.0000")
    assert sb.t_score == Decimal("50.0000")
    assert sb.risk_status == CycleScore.Risk.ON_TRACK
    # C
    assert sc.raw_score == Decimal("0.3000")
    assert sc.z_score == Decimal("-1.2250")
    assert sc.t_score == Decimal("37.7500")
    assert sc.risk_status == CycleScore.Risk.AT_RISK


def test_critical_tier_exercised():
    """A low outlier among five top performers drives t below T_CRITICAL.

        raws = [1.0, 1.0, 1.0, 1.0, 1.0, 0.0]
        mean = 5.0 / 6 = 0.8333 (4dp)
        var  = (5*(1.0-0.8333)^2 + (0-0.8333)^2)/6 ; std = sqrt(var) -> 0.3727
        outlier z = (0 - 0.8333)/0.3727 = -2.2358 -> t = 27.6420 < 30 -> CRITICAL
    """
    t = TenantFactory()
    cyc = CycleFactory(tenant=t)
    tops = [_simple_employee(t, cyc, "100.0000") for _ in range(5)]  # raw 1.0000 each
    low = _simple_employee(t, cyc, "0.0000")  # raw 0.0000

    compute_cycle_scores(t.id, cyc.id)

    s_low = _score_for(t, cyc, low)
    assert s_low.raw_score == Decimal("0.0000")
    assert s_low.z_score == Decimal("-2.2358")
    assert s_low.t_score == Decimal("27.6420")
    assert s_low.risk_status == CycleScore.Risk.CRITICAL
    # the top performers are ON_TRACK
    for emp in tops:
        assert _score_for(t, cyc, emp).risk_status == CycleScore.Risk.ON_TRACK


# ── sigma == 0 (all equal raws) -> absolute-raw fallback ────────────────────
def test_zero_sigma_cohort_uses_absolute_fallback():
    """All three employees have identical raws -> std == 0 -> insufficient cohort.

    Z=0, T=50 for everyone; risk uses the ABSOLUTE raw fallback. We pick raws that
    land in each absolute tier:
        0.4 < ABS_CRITICAL(0.5)            -> CRITICAL  (engineered below)
    Here all three share raw 0.9 (>= ABS_AT_RISK 0.8) -> ON_TRACK.
    """
    t = TenantFactory()
    cyc = CycleFactory(tenant=t)
    emps = [_simple_employee(t, cyc, "90.0000") for _ in range(3)]  # all raw 0.9000

    compute_cycle_scores(t.id, cyc.id)

    for emp in emps:
        s = _score_for(t, cyc, emp)
        assert s.insufficient_cohort is True
        assert s.z_score == Decimal("0.0000")
        assert s.t_score == Decimal("50.0000")
        assert s.cohort_size == 3
        # absolute fallback: 0.9 >= 0.8 -> ON_TRACK
        assert s.risk_status == CycleScore.Risk.ON_TRACK


def test_zero_sigma_absolute_tiers_all_three():
    """sigma==0 fallback maps raw to each absolute tier (CRITICAL/AT_RISK/ON_TRACK)."""
    # Three separate single-tenant cohorts so each is uniform (std == 0).
    for value, expected in [
        ("40.0000", CycleScore.Risk.CRITICAL),   # raw 0.4 < 0.5
        ("70.0000", CycleScore.Risk.AT_RISK),    # 0.5 <= 0.7 < 0.8
        ("95.0000", CycleScore.Risk.ON_TRACK),   # 0.95 >= 0.8
    ]:
        t = TenantFactory()
        cyc = CycleFactory(tenant=t)
        emps = [_simple_employee(t, cyc, value) for _ in range(3)]
        compute_cycle_scores(t.id, cyc.id)
        for emp in emps:
            s = _score_for(t, cyc, emp)
            assert s.insufficient_cohort is True
            assert s.z_score == Decimal("0.0000")
            assert s.t_score == Decimal("50.0000")
            assert s.risk_status == expected


# ── cohort n < 2 -> insufficient, absolute fallback ─────────────────────────
def test_single_employee_cohort_insufficient():
    t = TenantFactory()
    cyc = CycleFactory(tenant=t)
    emp = _simple_employee(t, cyc, "30.0000")  # raw 0.3 < 0.5 -> CRITICAL fallback

    compute_cycle_scores(t.id, cyc.id)

    s = _score_for(t, cyc, emp)
    assert s.cohort_size == 1
    assert s.insufficient_cohort is True
    assert s.z_score == Decimal("0.0000")
    assert s.t_score == Decimal("50.0000")
    assert s.raw_score == Decimal("0.3000")
    assert s.risk_status == CycleScore.Risk.CRITICAL  # 0.3 < ABS_CRITICAL


# ── no-measurement KPI -> attainment 0 ──────────────────────────────────────
def test_no_measurement_attainment_zero():
    t = TenantFactory()
    cyc = CycleFactory(tenant=t)
    emp = UserFactory(tenant=t)
    goal = GoalFactory(employee=emp, cycle=cyc, weight=Decimal("100.00"), status="ACTIVE")
    kpi = KpiFactory(goal=goal, weight=Decimal("100.00"), target_value=Decimal("100.0000"))
    # no KpiMeasurement created
    with tenant_context(t):
        assert kpi_attainment(kpi) == Decimal("0.0000")
        assert goal_raw_score(goal) == Decimal("0.0000")
        assert employee_raw_score(emp.id, cyc.id) == Decimal("0.0000")


def test_latest_measurement_wins_by_recorded_at():
    """The engine reads the latest measurement (recorded_at desc, created_at desc)."""
    t = TenantFactory()
    cyc = CycleFactory(tenant=t)
    emp = UserFactory(tenant=t)
    goal = GoalFactory(employee=emp, cycle=cyc, weight=Decimal("100.00"), status="ACTIVE")
    kpi = KpiFactory(goal=goal, weight=Decimal("100.00"), target_value=Decimal("100.0000"))
    older = timezone.now() - datetime.timedelta(days=10)
    newer = timezone.now()
    KpiMeasurementFactory(kpi=kpi, value=Decimal("20.0000"), recorded_at=older)
    KpiMeasurementFactory(kpi=kpi, value=Decimal("80.0000"), recorded_at=newer)
    with tenant_context(t):
        # latest is 80 -> attainment 0.8
        assert kpi_attainment(kpi) == Decimal("0.8000")


# ── DECREASING direction ────────────────────────────────────────────────────
def test_decreasing_actual_below_target_is_overdelivery():
    """DECREASING: attainment = target/actual. actual < target -> > 1 (clamped)."""
    t = TenantFactory()
    cyc = CycleFactory(tenant=t)
    emp = UserFactory(tenant=t)
    goal = GoalFactory(employee=emp, cycle=cyc, weight=Decimal("100.00"), status="ACTIVE")
    # target 10, actual 8 -> 10/8 = 1.25 (under cap)
    kpi = KpiFactory(
        goal=goal, weight=Decimal("100.00"), target_value=Decimal("10.0000"),
        direction="DECREASING",
    )
    KpiMeasurementFactory(kpi=kpi, value=Decimal("8.0000"), recorded_at=timezone.now())
    with tenant_context(t):
        assert kpi_attainment(kpi) == Decimal("1.2500")


def test_decreasing_actual_zero_is_cap():
    """DECREASING: actual == 0 (drove it to zero) -> attainment == cap (1.5)."""
    t = TenantFactory()
    cyc = CycleFactory(tenant=t)
    emp = UserFactory(tenant=t)
    goal = GoalFactory(employee=emp, cycle=cyc, weight=Decimal("100.00"), status="ACTIVE")
    kpi = KpiFactory(
        goal=goal, weight=Decimal("100.00"), target_value=Decimal("10.0000"),
        direction="DECREASING",
    )
    KpiMeasurementFactory(kpi=kpi, value=Decimal("0.0000"), recorded_at=timezone.now())
    with tenant_context(t):
        assert kpi_attainment(kpi) == C.ATTAINMENT_CAP.quantize(Decimal("0.0001"))
        assert kpi_attainment(kpi) == Decimal("1.5000")


def test_decreasing_actual_far_below_target_clamped_at_cap():
    """DECREASING: target/actual far above cap -> clamped to 1.5."""
    t = TenantFactory()
    cyc = CycleFactory(tenant=t)
    emp = UserFactory(tenant=t)
    goal = GoalFactory(employee=emp, cycle=cyc, weight=Decimal("100.00"), status="ACTIVE")
    # target 100, actual 1 -> 100/1 = 100 -> clamp to 1.5
    kpi = KpiFactory(
        goal=goal, weight=Decimal("100.00"), target_value=Decimal("100.0000"),
        direction="DECREASING",
    )
    KpiMeasurementFactory(kpi=kpi, value=Decimal("1.0000"), recorded_at=timezone.now())
    with tenant_context(t):
        assert kpi_attainment(kpi) == Decimal("1.5000")


# ── INCREASING attainment clamp at cap ──────────────────────────────────────
def test_increasing_attainment_clamped_at_cap():
    """INCREASING: actual >> target -> attainment clamped to cap 1.5."""
    t = TenantFactory()
    cyc = CycleFactory(tenant=t)
    emp = UserFactory(tenant=t)
    goal = GoalFactory(employee=emp, cycle=cyc, weight=Decimal("100.00"), status="ACTIVE")
    # target 100, actual 1000 -> 10.0 -> clamp to 1.5
    kpi = KpiFactory(goal=goal, weight=Decimal("100.00"), target_value=Decimal("100.0000"))
    KpiMeasurementFactory(kpi=kpi, value=Decimal("1000.0000"), recorded_at=timezone.now())
    with tenant_context(t):
        assert kpi_attainment(kpi) == Decimal("1.5000")


# ── pace_behind ─────────────────────────────────────────────────────────────
def test_pace_behind_true_when_below_elapsed_threshold():
    """ACTIVE cycle, raw below elapsed_fraction * PACE_SHORTFALL -> behind pace.

    Cycle Jan1..Mar31; as_of=Mar31 -> elapsed 1.0; threshold = 1.0 * 0.7 = 0.7.
    raw 0.3 < 0.7 -> True. Does NOT change the tier (asserted via fallback risk).
    """
    t = TenantFactory()
    cyc = CycleFactory(
        tenant=t, start_date=datetime.date(2026, 1, 1), end_date=datetime.date(2026, 3, 31),
        status="ACTIVE",
    )
    emp = _simple_employee(t, cyc, "30.0000")  # raw 0.3
    as_of = datetime.date(2026, 3, 31)
    compute_cycle_scores(t.id, cyc.id, as_of=as_of)
    s = _score_for(t, cyc, emp)
    assert s.pace_behind is True
    # single-employee cohort -> absolute fallback; 0.3 < 0.5 -> CRITICAL,
    # and pace did NOT alter it.
    assert s.risk_status == CycleScore.Risk.CRITICAL


def test_pace_behind_false_when_ahead():
    """raw comfortably above the elapsed pace threshold -> not behind."""
    t = TenantFactory()
    cyc = CycleFactory(
        tenant=t, start_date=datetime.date(2026, 1, 1), end_date=datetime.date(2026, 3, 31),
        status="ACTIVE",
    )
    emp = _simple_employee(t, cyc, "90.0000")  # raw 0.9
    as_of = datetime.date(2026, 3, 31)  # elapsed 1.0 -> threshold 0.7; 0.9 >= 0.7
    compute_cycle_scores(t.id, cyc.id, as_of=as_of)
    s = _score_for(t, cyc, emp)
    assert s.pace_behind is False


def test_pace_does_not_change_tier():
    """A strong performer flagged behind-pace stays ON_TRACK (pace is orthogonal).

    Build a real cohort (sigma>0) where the top performer is ON_TRACK by T-score,
    yet behind pace because the cycle is fully elapsed and raw < 0.7-of-elapsed.
    """
    t = TenantFactory()
    cyc = CycleFactory(
        tenant=t, start_date=datetime.date(2026, 1, 1), end_date=datetime.date(2026, 3, 31),
        status="ACTIVE",
    )
    # raws 0.6, 0.3, 0.3 -> top (0.6) is clearly highest. elapsed=1.0, thr=0.7.
    top = _simple_employee(t, cyc, "60.0000")
    _simple_employee(t, cyc, "30.0000")
    _simple_employee(t, cyc, "30.0000")
    compute_cycle_scores(t.id, cyc.id, as_of=datetime.date(2026, 3, 31))
    s = _score_for(t, cyc, top)
    # 0.6 < 0.7 threshold -> behind pace
    assert s.pace_behind is True
    # but T-score keeps it out of CRITICAL (highest in cohort) — assert not CRITICAL
    assert s.risk_status != CycleScore.Risk.CRITICAL


def test_pace_not_behind_on_inactive_cycle():
    """A non-ACTIVE cycle is never 'behind pace', whatever the raw."""
    t = TenantFactory()
    cyc = CycleFactory(tenant=t, status="CLOSED")
    with tenant_context(t):
        assert pace_behind(cyc, Decimal("0.0000")) is False


# ── IDEMPOTENCY ─────────────────────────────────────────────────────────────
def test_idempotent_recompute():
    """Running twice yields identical score fields and NO duplicate rows."""
    t = TenantFactory()
    cyc = CycleFactory(tenant=t)
    a = _simple_employee(t, cyc, "90.0000")
    b = _simple_employee(t, cyc, "60.0000")
    c = _simple_employee(t, cyc, "30.0000")

    compute_cycle_scores(t.id, cyc.id)
    with tenant_context(t):
        first = {
            s.employee_id: (s.raw_score, s.z_score, s.t_score, s.risk_status, s.cohort_size)
            for s in CycleScore.objects.filter(cycle_id=cyc.id)
        }
        count_first = CycleScore.objects.filter(cycle_id=cyc.id).count()

    compute_cycle_scores(t.id, cyc.id)
    with tenant_context(t):
        second = {
            s.employee_id: (s.raw_score, s.z_score, s.t_score, s.risk_status, s.cohort_size)
            for s in CycleScore.objects.filter(cycle_id=cyc.id)
        }
        count_second = CycleScore.objects.filter(cycle_id=cyc.id).count()

    assert count_first == 3
    assert count_second == 3  # no duplicates
    assert first == second  # identical score fields
    assert {a.id, b.id, c.id} == set(first)


def test_task_entry_point_runs_synchronously():
    """Calling the shared_task as a plain function runs the engine inline."""
    t = TenantFactory()
    cyc = CycleFactory(tenant=t)
    emp = _simple_employee(t, cyc, "90.0000")
    rows = recompute_cycle_scores(t.id, cyc.id)
    assert len(rows) == 1
    s = _score_for(t, cyc, emp)
    assert s.raw_score == Decimal("0.9000")


# ── Decimal precision (no float drift) ──────────────────────────────────────
def test_decimal_exactness_one_third_attainment():
    """A 1/3-style attainment stays an exact 4-dp Decimal — no float drift."""
    t = TenantFactory()
    cyc = CycleFactory(tenant=t)
    emp = UserFactory(tenant=t)
    goal = GoalFactory(employee=emp, cycle=cyc, weight=Decimal("100.00"), status="ACTIVE")
    # target 3, actual 1 -> 1/3 = 0.333333... -> quantized 0.3333
    kpi = KpiFactory(goal=goal, weight=Decimal("100.00"), target_value=Decimal("3.0000"))
    KpiMeasurementFactory(kpi=kpi, value=Decimal("1.0000"), recorded_at=timezone.now())
    with tenant_context(t):
        att = kpi_attainment(kpi)
        assert isinstance(att, Decimal)
        assert att == Decimal("0.3333")


def test_results_are_decimal_not_float():
    t = TenantFactory()
    cyc = CycleFactory(tenant=t)
    _simple_employee(t, cyc, "90.0000")
    _simple_employee(t, cyc, "60.0000")
    _simple_employee(t, cyc, "30.0000")
    compute_cycle_scores(t.id, cyc.id)
    with tenant_context(t):
        for s in CycleScore.objects.filter(cycle_id=cyc.id):
            assert isinstance(s.raw_score, Decimal)
            assert isinstance(s.z_score, Decimal)
            assert isinstance(s.t_score, Decimal)


def test_population_mean_std_exact():
    """population_mean_std is Decimal-exact (population sigma, divisor n)."""
    mean, std = population_mean_std([Decimal("0.9"), Decimal("0.6"), Decimal("0.3")])
    assert mean == Decimal("0.6000")
    assert std == Decimal("0.2449")  # sqrt(0.06) quantized 4dp
    # single value -> std 0
    m1, s1 = population_mean_std([Decimal("0.5")])
    assert m1 == Decimal("0.5000")
    assert s1 == Decimal("0.0000")


def test_normalize_insufficient_when_no_spread():
    z, t, insufficient = normalize(Decimal("0.5"), Decimal("0.5"), Decimal("0"))
    assert (z, t, insufficient) == (Decimal("0.0000"), Decimal("50.0000"), True)


def test_risk_status_direct():
    # cohort path on T
    assert risk_status(Decimal("29"), Decimal("0"), False) == CycleScore.Risk.CRITICAL
    assert risk_status(Decimal("35"), Decimal("0"), False) == CycleScore.Risk.AT_RISK
    assert risk_status(Decimal("50"), Decimal("0"), False) == CycleScore.Risk.ON_TRACK
    # absolute fallback on raw
    assert risk_status(Decimal("50"), Decimal("0.4"), True) == CycleScore.Risk.CRITICAL
    assert risk_status(Decimal("50"), Decimal("0.7"), True) == CycleScore.Risk.AT_RISK
    assert risk_status(Decimal("50"), Decimal("0.9"), True) == CycleScore.Risk.ON_TRACK


# ── only ACTIVE goals count ─────────────────────────────────────────────────
def test_only_active_goals_contribute_to_raw():
    t = TenantFactory()
    cyc = CycleFactory(tenant=t)
    emp = UserFactory(tenant=t)
    active = GoalFactory(employee=emp, cycle=cyc, weight=Decimal("100.00"), status="ACTIVE")
    KpiFactory(goal=active, weight=Decimal("100.00"), target_value=Decimal("100.0000"))
    # a DRAFT goal that must be ignored entirely
    draft = GoalFactory(employee=emp, cycle=cyc, weight=Decimal("100.00"), status="DRAFT")
    dk = KpiFactory(goal=draft, weight=Decimal("100.00"), target_value=Decimal("100.0000"))
    with tenant_context(t):
        KpiMeasurementFactory(kpi=dk, value=Decimal("100.0000"), recorded_at=timezone.now())
        # active goal has no measurement -> 0; draft is ignored -> total raw 0
        assert employee_raw_score(emp.id, cyc.id) == Decimal("0.0000")
    # the cohort should not include this employee... actually it SHOULD (active goal
    # exists) but with raw 0. Confirm via the orchestrator.
    compute_cycle_scores(t.id, cyc.id)
    s = _score_for(t, cyc, emp)
    assert s.raw_score == Decimal("0.0000")


# ── COHORT TENANT ISOLATION ─────────────────────────────────────────────────
def test_cohort_tenant_isolation():
    """Two tenants, same-named cycle. Tenant B's huge raw must NOT move A's Z/T.

    Tenant A cohort: raws 0.9, 0.6, 0.3 (the golden cohort) -> A's top employee
    has t=62.25. Tenant B has an enormous extra spread (raws 1.5 and 0.0). If the
    cohorts leaked, A's mean/std (and thus Z/T) would shift. We assert A's scores
    are EXACTLY the isolated golden values.
    """
    a = TenantFactory()
    b = TenantFactory()
    cyc_a = CycleFactory(tenant=a, name="FY26 Q1")
    cyc_b = CycleFactory(tenant=b, name="FY26 Q1")  # same name, different tenant

    # Tenant A: golden cohort.
    ea1 = _simple_employee(a, cyc_a, "90.0000")
    _simple_employee(a, cyc_a, "60.0000")
    ea3 = _simple_employee(a, cyc_a, "30.0000")

    # Tenant B: a wildly different cohort (max attainment + zero).
    _simple_employee(b, cyc_b, "1000.0000")  # clamps to raw 1.5
    _simple_employee(b, cyc_b, "0.0000")     # raw 0.0

    # Compute B first, then A — order must not matter.
    compute_cycle_scores(b.id, cyc_b.id)
    compute_cycle_scores(a.id, cyc_a.id)

    sa1 = _score_for(a, cyc_a, ea1)
    sa3 = _score_for(a, cyc_a, ea3)
    # A's golden numbers, unperturbed by tenant B.
    assert sa1.cohort_size == 3
    assert sa1.z_score == Decimal("1.2250")
    assert sa1.t_score == Decimal("62.2500")
    assert sa3.z_score == Decimal("-1.2250")
    assert sa3.t_score == Decimal("37.7500")
    # And A only ever produced 3 CycleScore rows (no leak of B's employees).
    with tenant_context(a):
        assert CycleScore.objects.filter(cycle_id=cyc_a.id).count() == 3


# ── SEAM: cycle_scores_recomputed fires with the per-employee risk dicts ────
def test_signal_seam_fires_once_with_scores():
    t = TenantFactory()
    cyc = CycleFactory(tenant=t)
    a = _simple_employee(t, cyc, "90.0000")
    b = _simple_employee(t, cyc, "60.0000")
    c = _simple_employee(t, cyc, "30.0000")

    received = []

    def receiver(sender, **kwargs):
        received.append(kwargs)

    cycle_scores_recomputed.connect(receiver)
    try:
        compute_cycle_scores(t.id, cyc.id)
    finally:
        cycle_scores_recomputed.disconnect(receiver)

    assert len(received) == 1
    payload = received[0]
    assert payload["tenant_id"] == str(t.id)
    assert payload["cycle_id"] == str(cyc.id)
    scores = payload["scores"]
    assert isinstance(scores, list)
    assert len(scores) == 3
    # every per-employee dict carries the risk fields the nudge layer needs
    by_emp = {s["employee_id"]: s for s in scores}
    assert {a.id, b.id, c.id} == set(by_emp)
    for s in scores:
        assert set(s) == {
            "employee_id", "raw_score", "z_score", "t_score",
            "risk_status", "pace_behind", "insufficient_cohort", "cohort_size",
        }
        assert isinstance(s["raw_score"], Decimal)
        assert s["cohort_size"] == 3
    # the AT_RISK member (raw 0.3) is reflected in the payload
    assert by_emp[c.id]["risk_status"] == CycleScore.Risk.AT_RISK
    assert by_emp[a.id]["risk_status"] == CycleScore.Risk.ON_TRACK
