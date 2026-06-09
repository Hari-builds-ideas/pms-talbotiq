"""
Named, tunable constants for the deterministic T/Z scoring engine.

EVERY numeric ratio / threshold is a ``Decimal`` — never a float — so the engine
is fully reproducible (no binary-float drift). These are the only knobs scoring
behaviour turns on; the engine itself hard-codes nothing. Tuning a threshold here
changes scoring everywhere consistently.
"""
from decimal import Decimal

# ── Attainment bounds ───────────────────────────────────────────────────────
# A KPI's attainment (actual vs target) is clamped to this closed interval.
# Floor at 0 (no negative credit); cap at 1.5 (over-delivery credit is capped so
# one runaway KPI cannot dominate a goal/cohort).
ATTAINMENT_FLOOR = Decimal("0")
ATTAINMENT_CAP = Decimal("1.5")

# ── Risk tiers on the normalized T-score (cohort path, n>=2 and std>0) ──────
# t < T_CRITICAL            -> CRITICAL
# T_CRITICAL <= t < T_AT_RISK -> AT_RISK
# t >= T_AT_RISK            -> ON_TRACK
T_CRITICAL = Decimal("30")
T_AT_RISK = Decimal("40")

# ── Risk tiers on the ABSOLUTE raw score (fallback when the cohort is too small
# or has no spread, so a T-score is not meaningful). raw is on the [0, cap] scale.
# raw < ABS_CRITICAL          -> CRITICAL
# ABS_CRITICAL <= raw < ABS_AT_RISK -> AT_RISK
# raw >= ABS_AT_RISK          -> ON_TRACK
ABS_CRITICAL = Decimal("0.5")
ABS_AT_RISK = Decimal("0.8")

# ── Pace check ──────────────────────────────────────────────────────────────
# An employee is "behind pace" (separate boolean, does NOT change the risk tier)
# when raw < elapsed_fraction * PACE_SHORTFALL on an ACTIVE cycle. The 0.7 factor
# allows realistic back-loaded delivery before flagging.
PACE_SHORTFALL = Decimal("0.7")

# ── Decimal rounding granularities ──────────────────────────────────────────
# Internal intermediate results are quantized to 4 dp; display values to 2 dp.
INTERNAL_DP = Decimal("0.0001")
DISPLAY_DP = Decimal("0.01")
