"""
The deterministic succession engine — pure mappings (readiness, 9-box, coverage)
and the DB-backed analysis. No AI; this is the always-available core.
"""
from decimal import Decimal

import pytest

from apps.succession import constants as C
from apps.succession import engine

# ── performance band from T-score (the Module-2 CycleScore) ──────────────────


@pytest.mark.parametrize(
    "t, band",
    [
        (Decimal("39"), C.BAND_LOW),
        (Decimal("39.9999"), C.BAND_LOW),
        (Decimal("40"), C.BAND_MEDIUM),   # 40 <= t <= 60 -> MEDIUM (inclusive)
        (Decimal("50"), C.BAND_MEDIUM),
        (Decimal("60"), C.BAND_MEDIUM),
        (Decimal("60.0001"), C.BAND_HIGH),
        (Decimal("70"), C.BAND_HIGH),
        (None, C.BAND_UNKNOWN),
    ],
)
def test_performance_band_from_tscore(t, band):
    assert engine.performance_band_from_tscore(t) == band


# ── 9-box numbering ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "perf, pot, box",
    [
        (C.BAND_LOW, C.BAND_LOW, 1),
        (C.BAND_LOW, C.BAND_MEDIUM, 2),
        (C.BAND_LOW, C.BAND_HIGH, 3),
        (C.BAND_MEDIUM, C.BAND_LOW, 4),
        (C.BAND_MEDIUM, C.BAND_MEDIUM, 5),
        (C.BAND_MEDIUM, C.BAND_HIGH, 6),
        (C.BAND_HIGH, C.BAND_LOW, 7),
        (C.BAND_HIGH, C.BAND_MEDIUM, 8),
        (C.BAND_HIGH, C.BAND_HIGH, 9),
    ],
)
def test_compute_box(perf, pot, box):
    assert engine.compute_box(perf, pot) == box


# ── readiness default mapping ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "perf, pot, readiness",
    [
        (C.BAND_HIGH, C.BAND_HIGH, C.READY_NOW),
        (C.BAND_HIGH, C.BAND_MEDIUM, C.READY_SOON),
        (C.BAND_MEDIUM, C.BAND_HIGH, C.READY_SOON),
        (C.BAND_MEDIUM, C.BAND_MEDIUM, C.READY_SOON),
        (C.BAND_MEDIUM, C.BAND_LOW, C.DEVELOPING),
        (C.BAND_HIGH, C.BAND_LOW, C.DEVELOPING),
        (C.BAND_LOW, C.BAND_HIGH, C.NOT_READY),   # LOW perf is never ready
        (C.BAND_LOW, C.BAND_LOW, C.NOT_READY),
        (C.BAND_UNKNOWN, C.BAND_HIGH, C.NOT_READY),  # no score -> NOT_READY
    ],
)
def test_default_readiness(perf, pot, readiness):
    assert engine.default_readiness(perf, pot) == readiness


def test_default_readiness_missing_potential_treated_as_low():
    # No 9-box potential -> conservative LOW; a HIGH performer is at best DEVELOPING.
    assert engine.default_readiness(C.BAND_HIGH, None) == C.DEVELOPING
    assert engine.default_readiness(C.BAND_LOW, None) == C.NOT_READY


# ── coverage ─────────────────────────────────────────────────────────────────


def test_coverage_green_amber_red():
    assert engine.coverage_from_readinesses([C.NOT_READY, C.READY_NOW]) == C.COVERAGE_GREEN
    assert engine.coverage_from_readinesses([C.DEVELOPING, C.READY_SOON]) == C.COVERAGE_AMBER
    assert engine.coverage_from_readinesses([C.DEVELOPING, C.NOT_READY]) == C.COVERAGE_RED
    assert engine.coverage_from_readinesses([]) == C.COVERAGE_RED  # empty bench is RED
