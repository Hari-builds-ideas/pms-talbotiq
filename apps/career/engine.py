"""
The DETERMINISTIC career engine — skill gap + advisory tiered roadmap. No AI.

This is CORE: it works without the Career Roadmap agent (Module 10) and is always
available. The agent (Module 10) only ENRICHES the deterministic baseline into a
new ``source=AI`` roadmap; it never replaces this.

THE DATA BOUNDARY (re-stated, because it is the safety property of this module):
the engine reads ONLY the subject employee's OWN performance data —
  * their ``CycleScore`` (via the Module-8 ``performance_band_from_tscore`` band
    math — this is the readiness-math reuse the spec asks for), and
  * their ``Goal``/``Kpi`` attainment (via the Module-2 ``goal_raw_score``),
both of which the employee is already entitled to see about themselves. It does
NOT read or surface the sensitive succession surface — ``BenchCandidate``,
``CriticalRole``, ``SuccessionPlan``, or the 9-box ``NineBoxPlacement`` potential —
so a career response can never leak another person's data or a management-only
talent assessment. (The "current potential band" and "readiness" labels are
succession constructs and are deliberately ABSENT from everything this engine
returns.)

Functions that read the ORM must run inside a bound tenant context (the callers
bind it).
"""
from __future__ import annotations

# Reuse, don't fork: the Module-8 performance-band math (reads CycleScore only) and
# the Module-2 per-goal attainment. These are the only cross-module reads, and both
# are over the employee's OWN performance data.
from apps.goals.models import Goal
from apps.goals.scoring.engine import goal_raw_score
from apps.succession.engine import latest_cyclescore, performance_band_for

from . import constants as C


# ── skill gap (employee's OWN performance data only) ──────────────────────────


def _target_cycle_id(employee_id):
    """The cycle of the employee's most recent ``CycleScore``, or None. Weak-goal
    detection runs against this cycle so the gap reflects current performance."""
    score = latest_cyclescore(employee_id)
    return score.cycle_id if score else None


def weak_goal_categories(employee_id) -> list[dict]:
    """The employee's ACTIVE goals (in their latest scored cycle) whose Module-2
    raw attainment is below the weak threshold — these are the development
    "categories". Reuses ``goal_raw_score`` so "weak" means exactly the Module-2
    at-risk definition. Reads the employee's OWN goals only."""
    cycle_id = _target_cycle_id(employee_id)
    if cycle_id is None:
        return []
    weak = []
    for goal in Goal.objects.filter(
        employee_id=employee_id, cycle_id=cycle_id, status=Goal.Status.ACTIVE
    ):
        raw = goal_raw_score(goal)
        if raw < C.WEAK_GOAL_THRESHOLD:
            weak.append(
                {"goal": goal.title, "goal_id": str(goal.id), "raw_score": str(raw)}
            )
    return weak


def compute_skill_gap(employee_id) -> dict:
    """The deterministic skill gap for ``employee_id`` toward a target role.

    Built ENTIRELY from the employee's own performance data:
      * ``current_performance_band`` — from their latest CycleScore T-score
        (Module-8 band math). UNKNOWN when they have no score yet.
      * ``required_performance_band`` — the LITE rule: a target role asks for
        sustained HIGH performance.
      * ``performance_band_gap`` — 0/1/2 band-distance to the requirement.
      * ``weak_categories`` — at-risk goal categories from Module 2.

    Deliberately contains NO potential band, NO readiness label, NO bench/coverage
    — those are the management-only succession surface (see the module docstring).
    """
    current_band = performance_band_for(employee_id)
    required_band = C.REQUIRED_PERFORMANCE_BAND
    gap = C.BAND_GAP_INDEX[required_band] - C.BAND_GAP_INDEX[current_band]
    performance_band_gap = gap if gap > 0 else 0
    return {
        "current_performance_band": current_band,
        "required_performance_band": required_band,
        "performance_band_gap": performance_band_gap,
        "weak_categories": weak_goal_categories(employee_id),
    }


# ── advisory tiered roadmap (deterministic) ───────────────────────────────────


def build_roadmap_tiers(gap: dict, *, target_label: str) -> list[dict]:
    """Build the ordered, deterministic development tiers from a computed ``gap``.

    Reproducible: the same gap + label always yields the same tiers. Each tier
    carries a ``basis`` code naming the deterministic reason it exists. The tiers
    are advisory development steps — never a promotion instruction.
    """
    tiers: list[dict] = []
    band_gap = gap["performance_band_gap"]
    current = gap["current_performance_band"]

    # 1. Performance-band tiers — one step per band still to climb toward HIGH.
    if current == C.BAND_UNKNOWN:
        tiers.append(
            {
                "title": "Establish a measured performance baseline",
                "detail": (
                    "You have no scored cycle yet. Agree goals + KPIs for the "
                    "current cycle so your performance can be measured."
                ),
                "basis": C.BASIS_PERFORMANCE,
            }
        )
    if band_gap >= 2:
        tiers.append(
            {
                "title": "Reach MEDIUM sustained performance",
                "detail": "Lift your cycle performance into the MEDIUM band and hold it.",
                "basis": C.BASIS_PERFORMANCE,
            }
        )
    if band_gap >= 1:
        tiers.append(
            {
                "title": "Reach HIGH sustained performance",
                "detail": (
                    f"The target role ({target_label}) expects sustained HIGH "
                    "performance — close the remaining band gap."
                ),
                "basis": C.BASIS_PERFORMANCE,
            }
        )

    # 2. A tier per weak KPI/goal category (Module-2 at-risk goals).
    for cat in gap["weak_categories"]:
        tiers.append(
            {
                "title": f"Close the KPI gap in “{cat['goal']}”",
                "detail": (
                    f"This goal is below target (raw {cat['raw_score']}). Improving "
                    "it strengthens your preparedness for the target role."
                ),
                "basis": C.BASIS_KPI_CATEGORY,
            }
        )

    # 3. Demonstrate growth via a stretch assignment (always advisory). NB: the
    #    copy deliberately avoids the words "potential"/"readiness" — those are
    #    management-only succession constructs and never appear in career output;
    #    this is generic coaching, and we never read/reveal any 9-box rating.
    tiers.append(
        {
            "title": "Demonstrate growth through a stretch assignment",
            "detail": (
                "Take on scope beyond your current role (lead a project, mentor a "
                "peer) to evidence your preparedness for the next level."
            ),
            "basis": C.BASIS_GROWTH,
        }
    )

    # 4. A final stretch goal aligned to the target role.
    tiers.append(
        {
            "title": f"Complete a stretch goal aligned to {target_label}",
            "detail": (
                "Agree a stretch goal with your manager that mirrors the target "
                "role's responsibilities."
            ),
            "basis": C.BASIS_STRETCH,
        }
    )

    # Stamp a stable 0-based ordering.
    for i, tier in enumerate(tiers):
        tier["index"] = i
    return tiers
