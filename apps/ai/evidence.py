"""
Evidence builders — the RICH, real context each human-read agent feeds its
prompt. Kept here (not scattered through the agent nodes) so the "what does the
model actually see" decision is one tunable, reviewable seam.

Every builder reads through the TENANT-SCOPED managers (the agent tasks run
inside ``tenant_context``), returns plain JSON-able dicts, and includes ONLY data
the agent is allowed to ground on:
  * a REVIEW may name its subject and cite that person's goals/KPIs/score;
  * a FEEDBACK summary never sees identities (it consumes the anonymised payload
    directly — there is deliberately no builder here for it);
  * succession / career builders carry performance-derived signals only, never
    another employee's private data.

Builders also report an ``evidence_sufficiency`` hint (0..1) so an agent can lower
its confidence when the grounding is thin (no goals, no score) — the existing
low-confidence warning + HITL gate then apply.
"""
from __future__ import annotations

from decimal import Decimal


def _subject_name(user) -> str:
    """The subject's first name for the prompt (names are not PII for a review of
    that person). Falls back to a neutral noun rather than a bare email (which the
    gateway would redact to an ugly token mid-sentence)."""
    name = getattr(user, "display_name", None)
    if name:
        return name.split()[0]
    return "the employee"


def _pct(ratio) -> int:
    try:
        return int(round(float(ratio) * 100))
    except (TypeError, ValueError):
        return 0


def _num(value) -> str | None:
    """A compact, human-readable number string: trim trailing zeros so a
    DecimalField's ``100.0000`` reads as ``100`` (cleaner AI citations)."""
    if value is None:
        return None
    try:
        d = Decimal(str(value)).normalize()
        # normalize() can yield exponent form (e.g. 1E+2) — expand it.
        return f"{d:f}"
    except Exception:  # noqa: BLE001 - formatting must never break evidence
        return str(value)


def review_evidence(review) -> dict:
    """Rich grounding for Agent 1: the subject's name, their goals (each with KPI
    target / latest actual / unit / attainment %), and their computed cycle score
    (T-score, risk band, pace, cohort). Reused as both the prompt input and the
    citation set."""
    from apps.goals.models import CycleScore, Goal
    from apps.goals.scoring.engine import kpi_attainment
    from apps.identity.models import User

    subject = User.objects.filter(pk=review.employee_id).first()
    name = _subject_name(subject) if subject else "the employee"

    goals_payload = []
    citations = []
    goals = Goal.objects.filter(
        employee_id=review.employee_id, cycle_id=review.cycle_id
    ).prefetch_related("kpis")
    for goal in goals:
        kpis = []
        for kpi in goal.kpis.all():
            latest = kpi.measurements.first()  # ordered -recorded_at
            kpis.append(
                {
                    "name": kpi.name,
                    "target": _num(kpi.target_value),
                    "actual": _num(latest.value) if latest else None,
                    "unit": kpi.unit or None,
                    "attainment_pct": _pct(kpi_attainment(kpi)),
                }
            )
        goals_payload.append(
            {
                "title": goal.title,
                "weight": str(goal.weight),
                "status": goal.status,
                "kpis": kpis,
            }
        )
        citations.append({"type": "goal", "title": goal.title})

    score = (
        CycleScore.objects.filter(
            employee_id=review.employee_id, cycle_id=review.cycle_id
        ).first()
    )
    score_payload = None
    if score:
        score_payload = {
            "t_score": f"{float(score.t_score):.1f}",
            "raw_score": _num(score.raw_score),
            "risk_status": score.risk_status,
            "pace_behind": score.pace_behind,
            "cohort_size": score.cohort_size,
            "insufficient_cohort": score.insufficient_cohort,
        }
        citations.append({"type": "cycle_score", "t_score": str(score.t_score)})

    # Sufficiency: real grounding needs goals (ideally with measured KPIs) AND a
    # score. Thin evidence → the agent lowers confidence.
    measured_kpis = sum(
        1 for g in goals_payload for k in g["kpis"] if k["actual"] is not None
    )
    if goals_payload and score_payload and measured_kpis:
        sufficiency = 1.0
    elif goals_payload and score_payload:
        sufficiency = 0.7
    elif goals_payload or score_payload:
        sufficiency = 0.5
    else:
        sufficiency = 0.2

    return {
        "subject_name": name,
        "goals": goals_payload,
        "score": score_payload,
        "citations": citations,
        "evidence_sufficiency": sufficiency,
    }


def succession_evidence(analysis: dict) -> dict:
    """A NAME-FREE summary of the deterministic succession analysis for Agent 4:
    bench size, readiness distribution, performance-band spread, coverage, and
    red-flag CODES. Strips candidate ids/emails entirely — the narrative reasons
    about coverage and bench depth, never individuals (defence in depth on top of
    the gateway's PII scrub)."""
    bench = analysis.get("ranked_bench", []) or []
    readiness_dist: dict[str, int] = {}
    band_dist: dict[str, int] = {}
    for row in bench:
        readiness_dist[row.get("readiness", "UNKNOWN")] = (
            readiness_dist.get(row.get("readiness", "UNKNOWN"), 0) + 1
        )
        band_dist[row.get("performance_band", "UNKNOWN")] = (
            band_dist.get(row.get("performance_band", "UNKNOWN"), 0) + 1
        )
    bench_size = len(bench)
    # Sufficiency: a real bench with some ready depth grounds a confident
    # narrative; an empty / single-name bench does not.
    if bench_size >= 3:
        sufficiency = 1.0
    elif bench_size == 2:
        sufficiency = 0.8
    elif bench_size == 1:
        sufficiency = 0.55
    else:
        sufficiency = 0.35
    return {
        "bench_size": bench_size,
        "readiness_distribution": readiness_dist,
        "performance_band_distribution": band_dist,
        "coverage_status": analysis.get("coverage_status"),
        "red_flag_codes": [f.get("code") for f in analysis.get("red_flags", [])],
        "evidence_sufficiency": sufficiency,
    }


def confidence_with_sufficiency(base: float | Decimal | None, sufficiency: float) -> float:
    """Blend a provider confidence with the evidence-sufficiency hint so a
    well-written answer on thin grounding still reads as lower confidence (and
    trips the floor warning). Multiplicative, clamped to [0, 1]."""
    try:
        b = float(base) if base is not None else 0.85
    except (TypeError, ValueError):
        b = 0.85
    return max(0.0, min(1.0, b * float(sufficiency)))
