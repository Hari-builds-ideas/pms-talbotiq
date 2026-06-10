"""
Tunable thresholds + deterministic mappings for the succession engine.

Everything here is data, no I/O — so the engine stays trivially testable and the
business rules live in one auditable place. The CycleScore T-score (Module 2) is
the single source of performance; potential is human-assigned (9-box).
"""
from __future__ import annotations

from decimal import Decimal

# ── performance band from a CycleScore T-score ───────────────────────────────
# t < 40 -> LOW ; 40 <= t <= 60 -> MEDIUM ; t > 60 -> HIGH.
T_LOW_MAX = Decimal("40")   # strictly below -> LOW
T_HIGH_MIN = Decimal("60")  # strictly above -> HIGH ; the closed [40, 60] band is MEDIUM

# Band / readiness string values (kept independent of the model TextChoices so the
# engine can be reasoned about as pure data; the model choices use the same
# strings, so they round-trip without translation).
BAND_LOW = "LOW"
BAND_MEDIUM = "MEDIUM"
BAND_HIGH = "HIGH"
#: Sentinel for "no CycleScore" — never stored on a 9-box, only used to drive
#: readiness to NOT_READY (a candidate with no score needs assessment).
BAND_UNKNOWN = "UNKNOWN"

READY_NOW = "READY_NOW"
READY_SOON = "READY_SOON"
DEVELOPING = "DEVELOPING"
NOT_READY = "NOT_READY"

COVERAGE_GREEN = "GREEN"
COVERAGE_AMBER = "AMBER"
COVERAGE_RED = "RED"

#: Band -> grid index (LOW=0, MEDIUM=1, HIGH=2) for 9-box numbering.
_BAND_INDEX = {BAND_LOW: 0, BAND_MEDIUM: 1, BAND_HIGH: 2}

#: Ranking weights (higher = better) for ordering a ranked bench.
READINESS_RANK = {READY_NOW: 3, READY_SOON: 2, DEVELOPING: 1, NOT_READY: 0}
PERFORMANCE_RANK = {BAND_HIGH: 3, BAND_MEDIUM: 2, BAND_LOW: 1, BAND_UNKNOWN: 0}
