"""
Tunable thresholds + deterministic mappings for the Career Development engine.

Data only, no I/O — so the engine stays trivially testable and the advisory
business rules live in one auditable place.

THE DATA BOUNDARY (the headline safety property of Module 9): career reuses the
Module-8 readiness *band math* (``performance_band_from_tscore`` over the Module-2
``CycleScore``) and the Module-2 per-goal attainment — both of which are the
employee's OWN performance data. It NEVER reads or surfaces the sensitive
succession surface (bench / 9-box potential / coverage / other employees). The
"required band" for any target role is a deterministic LITE rule (a target role
asks for sustained HIGH performance); per-role required profiles are a Phase-2 /
Agent (Module 10) refinement.
"""
from __future__ import annotations

from decimal import Decimal

# Reuse the Module-8 band strings + index so career and succession agree on the
# band vocabulary without redefining it (single source of truth in succession).
from apps.succession.constants import (  # noqa: F401  (re-exported for callers/tests)
    BAND_HIGH,
    BAND_LOW,
    BAND_MEDIUM,
    BAND_UNKNOWN,
    _BAND_INDEX,
)

#: The deterministic LITE requirement: to be ready for a target (more senior)
#: role you need sustained HIGH performance. A genuine per-role required profile
#: is Agent/Phase-2 work; the gap math here is band-distance to HIGH.
REQUIRED_PERFORMANCE_BAND = BAND_HIGH

#: Band -> a 0/1/2 index for gap arithmetic. UNKNOWN (no CycleScore) is treated as
#: the bottom (0) so an unscored employee shows the maximal, most conservative gap.
BAND_GAP_INDEX = {BAND_LOW: 0, BAND_MEDIUM: 1, BAND_HIGH: 2, BAND_UNKNOWN: 0}

#: A goal "category" is weak when its Module-2 raw attainment is below this. We
#: reuse the Module-2 ABS_AT_RISK threshold (0.8) so "weak here" means exactly
#: "at-risk there" — one definition of underperformance across the system.
from apps.goals.scoring.constants import ABS_AT_RISK as WEAK_GOAL_THRESHOLD  # noqa: E402

#: Roadmap tier basis codes — why a tier exists (deterministic provenance).
#: Deliberately NO "potential"/"readiness" vocabulary anywhere in career output:
#: those are management-only succession constructs, and keeping the career surface
#: literally free of that vocabulary makes the data boundary a trivially-auditable
#: invariant (a career response can never contain a succession token). See the
#: module docstring + ``engine.py``.
BASIS_PERFORMANCE = "PERFORMANCE_BAND_GAP"
BASIS_KPI_CATEGORY = "WEAK_KPI_CATEGORY"
BASIS_GROWTH = "DEMONSTRATE_GROWTH"
BASIS_STRETCH = "STRETCH_GOAL"

# The minimum decimal for a weak-score comparison is the Module-2 0.8 default; we
# keep it a Decimal so comparisons stay exact (no float drift).
assert isinstance(WEAK_GOAL_THRESHOLD, Decimal)
