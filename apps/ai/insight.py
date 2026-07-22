"""Data-grounded performance INSIGHT for the chat assistant.

The read-only assistant used to answer every "how is X?" with the same templated
goal list. This module turns real, RBAC-scoped data into *reasoned* answers:

  * ``person_facts``   — the structured, in-scope facts about one person
    (cycle status/pace, per-goal KPI attainment vs target, review load). This is
    the ONLY place chat reasoning is allowed to read performance data, and every
    read is gated by ``actor_can_access`` first — so intelligence can never reach
    past a caller's RBAC scope.
  * ``diagnose_person`` — a natural-language *diagnosis* ("is X on track / does X
    need help") derived deterministically from those facts. No fabrication: if a
    signal is missing we say so.
  * ``team_risk``       — a scoped scan of the caller's reporting subtree for the
    people who are at risk or behind pace ("who's behind on my team?").

Everything is deterministic and grounded; the Gemini phrasing layer (a later
increment) only ever rewords these same facts — it never adds data.
"""
from __future__ import annotations

from decimal import Decimal

from apps.rbac.scope import actor_can_access, reporting_subtree_ids


def _latest_measurement(kpi):
    return kpi.measurements.order_by("-recorded_at").first()


def _attainment_pct(kpi) -> float | None:
    """Latest KPI value as a % of target (direction-aware). None if not measurable."""
    m = _latest_measurement(kpi)
    if m is None or kpi.target_value in (None, Decimal("0")):
        return None
    try:
        value = float(m.value)
        target = float(kpi.target_value)
    except (TypeError, ValueError):
        return None
    if target == 0:
        return None
    if (kpi.direction or "").upper() == "DECREASING":
        # Lower is better: attainment is how far below/at target we are.
        return round((target / value) * 100, 1) if value else None
    return round((value / target) * 100, 1)


def person_facts(caller, target) -> dict | None:
    """Structured, in-scope facts for ``target``, or None if the caller may not see
    them. Read-only; tenant+RBAC scoped exactly like the rest of the assistant."""
    if target is None or not actor_can_access(caller, target):
        return None
    from apps.goals.models import CycleScore, Goal
    from apps.reviews.models import Review

    score = (
        CycleScore.objects.filter(employee_id=target.id)
        .order_by("-computed_at")
        .first()
    )
    goals = []
    for g in (
        Goal.objects.filter(employee_id=target.id, status="ACTIVE")
        .prefetch_related("kpis__measurements")
        .order_by("title")
    ):
        kpis = []
        for k in g.kpis.all():
            kpis.append({
                "name": k.name,
                "target": float(k.target_value) if k.target_value is not None else None,
                "unit": k.unit or "",
                "direction": (k.direction or "INCREASING").upper(),
                "attainment_pct": _attainment_pct(k),
            })
        goals.append({"title": g.title, "weight": float(g.weight or 0), "kpis": kpis})

    reviews = Review.objects.filter(employee_id=target.id)
    is_self = target.id == caller.id
    return {
        "name": "You" if is_self else target.display,
        "is_self": is_self,
        "has_score": score is not None,
        "risk_status": score.get_risk_status_display() if score else None,
        "risk_code": score.risk_status if score else None,
        "pace_behind": bool(score.pace_behind) if score else None,
        "goals": goals,
        "review_total": reviews.count(),
        "review_open": reviews.exclude(state="FINALIZED").count(),
    }


def _weakest_kpi(facts) -> tuple[str, str, float] | None:
    """The lowest-attainment measurable KPI across the person's goals: returns
    (goal_title, kpi_name, attainment_pct) or None when nothing is measured."""
    worst = None
    for g in facts["goals"]:
        for k in g["kpis"]:
            pct = k["attainment_pct"]
            if pct is None:
                continue
            if worst is None or pct < worst[2]:
                worst = (g["title"], k["name"], pct)
    return worst


def diagnose_person(caller, target) -> dict | None:
    """A reasoned status/diagnosis answer for ``target`` grounded in real data, or
    None if out of scope (the caller then shows the honest scope refusal)."""
    facts = person_facts(caller, target)
    if facts is None:
        return None

    who = facts["name"]
    verb = "are" if facts["is_self"] else "is"
    poss = "your" if facts["is_self"] else "their"

    if not facts["has_score"]:
        if not facts["goals"]:
            msg = (f"{who} {'have' if facts['is_self'] else 'has'} no active goals or "
                   "scored cycle yet, so there's nothing to assess this cycle.")
        else:
            titles = ", ".join(g["title"] for g in facts["goals"])
            msg = (f"{who} {verb} not scored yet this cycle, so I can't judge pace — "
                   f"but {poss} active goals are: {titles}.")
        return {"answer": msg, "facts": facts}

    status = facts["risk_status"]
    behind = facts["pace_behind"]
    on_track = facts["risk_code"] == "ON_TRACK"
    weak = _weakest_kpi(facts)

    # Lead line: the honest headline.
    if on_track and not behind:
        lead = f"{who} {verb} on track this cycle and keeping pace — no red flags."
    elif on_track and behind:
        lead = (f"{who} {verb} rated on track, but behind pace — so {'you' if facts['is_self'] else who} "
                f"could slip without attention.")
    else:  # at risk / needs support
        lead = f"{who} {verb} flagged {status.lower()}{' and behind pace' if behind else ''}."

    # Reasoning line: point at the weakest KPI if we have one.
    if weak:
        goal_title, kpi_name, pct = weak
        detail = (f" The weakest signal is “{kpi_name}” on “{goal_title}”, at {pct:.0f}% "
                  f"of target — that's the goal to focus on.")
    else:
        detail = (" No KPI measurements are recorded yet, so the rating is the only "
                  "signal — worth a check-in to add detail.")

    # Verdict for "does X need help?"
    needs_help = (not on_track) or behind or (weak is not None and weak[2] < 80)
    verdict = (
        f" Yes — {'you' if facts['is_self'] else who} likely {'need' if facts['is_self'] else 'needs'} support here."
        if needs_help
        else f" Overall, no extra help looks needed right now."
    )
    return {"answer": lead + detail + verdict, "facts": facts, "needs_help": needs_help}


def team_risk(caller) -> dict:
    """People in the caller's reporting subtree who are at risk or behind pace.
    Scoped: only the caller's own reports (never the whole tenant). Read-only."""
    from apps.goals.models import CycleScore
    from apps.identity.models import User

    ids = reporting_subtree_ids(caller) - {caller.id}
    if not ids:
        return {"manages": False, "flagged": [], "total": 0}

    people = {u.id: u for u in User.objects.filter(id__in=ids)}
    flagged = []
    for uid, user in people.items():
        score = (
            CycleScore.objects.filter(employee_id=uid)
            .order_by("-computed_at")
            .first()
        )
        if score is None:
            continue
        if score.risk_status != "ON_TRACK" or score.pace_behind:
            flagged.append({
                "name": user.display,
                "risk": score.get_risk_status_display(),
                "pace_behind": bool(score.pace_behind),
            })
    flagged.sort(key=lambda f: (f["risk"] == "On track", f["name"]))
    return {"manages": True, "flagged": flagged, "total": len(people)}
