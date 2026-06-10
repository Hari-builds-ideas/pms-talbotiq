"""
The DETERMINISTIC succession engine — readiness, 9-box, coverage. No AI.

This is CORE: it works without Agent 4 and is always available (ungated beyond
RBAC). Agent 4 (Module 10) only ENRICHES a generated plan into a new AI plan
locked PENDING_HUMAN_REVIEW; it never replaces this baseline.

Performance comes exclusively from the Module-2 ``CycleScore`` T-score; potential
is human-assigned via the 9-box. A candidate with no CycleScore resolves to
performance UNKNOWN -> readiness NOT_READY (needs assessment) — never a crash.

All thresholds + mappings live in ``constants.py`` (tunable). Functions that read
the ORM must run inside a bound tenant context (the callers bind it).
"""
from __future__ import annotations

from apps.goals.models import CycleScore

from . import constants as C
from .models import BenchCandidate, NineBoxPlacement


# ── pure mappings ─────────────────────────────────────────────────────────────


def performance_band_from_tscore(t_score) -> str:
    """Map a CycleScore T-score to a performance band:
    ``t < 40 -> LOW`` ; ``40 <= t <= 60 -> MEDIUM`` ; ``t > 60 -> HIGH``."""
    if t_score is None:
        return C.BAND_UNKNOWN
    if t_score < C.T_LOW_MAX:
        return C.BAND_LOW
    if t_score > C.T_HIGH_MIN:
        return C.BAND_HIGH
    return C.BAND_MEDIUM


def compute_box(performance_band: str, potential_band: str) -> int:
    """The 9-box cell (1–9) for ``(performance_band, potential_band)`` on the
    standard 3×3 grid:

        box = performance_index * 3 + potential_index + 1      (index: LOW=0, MED=1, HIGH=2)

    So LOW/LOW = 1, LOW/MED = 2, LOW/HIGH = 3, MED/LOW = 4, MED/MED = 5,
    MED/HIGH = 6, HIGH/LOW = 7, HIGH/MED = 8, HIGH/HIGH = 9 (the top-talent box).
    """
    perf_index = C._BAND_INDEX[performance_band]
    pot_index = C._BAND_INDEX[potential_band]
    return perf_index * 3 + pot_index + 1


def default_readiness(performance_band: str, potential_band: str | None) -> str:
    """The default readiness for a (performance, potential) pair. HRBP may OVERRIDE
    per candidate; an override is never recomputed away (see ``BenchCandidate``).

    Rules (decision 2): LOW perf (or no score) -> NOT_READY; HIGH+HIGH -> READY_NOW;
    (HIGH or MED) perf + (MED or HIGH) potential -> READY_SOON; MED perf +
    (LOW or MED) potential -> DEVELOPING. A missing potential is treated as LOW
    (conservative: unassessed potential never inflates readiness)."""
    pot = potential_band or C.BAND_LOW
    if performance_band in (C.BAND_UNKNOWN, C.BAND_LOW):
        return C.NOT_READY
    if performance_band == C.BAND_HIGH and pot == C.BAND_HIGH:
        return C.READY_NOW
    if performance_band in (C.BAND_HIGH, C.BAND_MEDIUM) and pot in (C.BAND_MEDIUM, C.BAND_HIGH):
        return C.READY_SOON
    if performance_band == C.BAND_MEDIUM and pot in (C.BAND_LOW, C.BAND_MEDIUM):
        return C.DEVELOPING
    # HIGH perf + LOW potential (high performer, unproven potential) -> DEVELOPING.
    return C.DEVELOPING


def coverage_from_readinesses(readinesses) -> str:
    """Coverage for a critical role from its bench's readiness values:
    any READY_NOW -> GREEN ; else any READY_SOON -> AMBER ; else RED (the spec's
    inadequate-coverage flag — an empty bench is RED)."""
    readinesses = list(readinesses)
    if C.READY_NOW in readinesses:
        return C.COVERAGE_GREEN
    if C.READY_SOON in readinesses:
        return C.COVERAGE_AMBER
    return C.COVERAGE_RED


# ── ORM-backed reads (caller binds tenant) ────────────────────────────────────


def latest_cyclescore(candidate_id):
    """The candidate's most recent CycleScore (by ``computed_at``), or None."""
    return (
        CycleScore.objects.filter(employee_id=candidate_id).order_by("-computed_at").first()
    )


def performance_band_for(candidate_id) -> str:
    """Performance band from the candidate's latest CycleScore (UNKNOWN if none)."""
    score = latest_cyclescore(candidate_id)
    return performance_band_from_tscore(score.t_score) if score else C.BAND_UNKNOWN


def latest_potential_band(candidate_id) -> str | None:
    """The candidate's most recently assessed 9-box potential band, or None."""
    placement = (
        NineBoxPlacement.objects.filter(employee_id=candidate_id)
        .order_by("-assessed_at")
        .first()
    )
    return placement.potential_band if placement else None


def computed_readiness_for(candidate_id) -> str:
    """The deterministic readiness for a candidate, from their latest CycleScore +
    latest 9-box potential."""
    return default_readiness(
        performance_band_for(candidate_id), latest_potential_band(candidate_id)
    )


def compute_analysis(critical_role) -> dict:
    """Produce the deterministic analysis for ``critical_role``.

    Recomputes readiness for every NON-overridden bench candidate (and persists
    it — overrides stick), then returns the ranked bench (by readiness, then
    performance), the coverage status, and any red flags. Caller binds the tenant.
    """
    analysed = []
    for bc in critical_role.bench.select_related("candidate"):
        perf = performance_band_for(bc.candidate_id)
        if not bc.readiness_overridden:
            new_readiness = computed_readiness_for(bc.candidate_id)
            if new_readiness != bc.readiness:
                bc.readiness = new_readiness
                bc.save(update_fields=["readiness", "updated_at"])
        analysed.append(
            {
                "candidate_id": str(bc.candidate_id),
                "candidate_email": bc.candidate.email,
                "readiness": bc.readiness,
                "performance_band": perf,
                "readiness_overridden": bc.readiness_overridden,
            }
        )

    analysed.sort(
        key=lambda r: (
            C.READINESS_RANK.get(r["readiness"], 0),
            C.PERFORMANCE_RANK.get(r["performance_band"], 0),
        ),
        reverse=True,
    )

    coverage = coverage_from_readinesses(r["readiness"] for r in analysed)
    red_flags = []
    if coverage == C.COVERAGE_RED:
        red_flags.append(
            {
                "code": "INADEQUATE_COVERAGE",
                "critical_role": str(critical_role.id),
                "detail": (
                    "No ready-now or ready-soon successor on the bench for a "
                    f"{critical_role.criticality} critical role."
                ),
            }
        )
    return {
        "ranked_bench": analysed,
        "coverage_status": coverage,
        "red_flags": red_flags,
    }
