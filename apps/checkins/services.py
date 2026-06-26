"""
Check-in services — the one place check-ins are written, read (scope-bound), and
responded to. Scope rules:
  * an employee writes/reads their OWN check-ins (author == caller);
  * a manager reads + responds to check-ins authored by someone in their reporting
    subtree (``actor_can_access``); out-of-scope / cross-manager → 404, cross-tenant
    impossible (TenantScopedManager).

Goal progress is PULLED READ-ONLY from the goals engine (``kpi_attainment``) — the
check-in never stores or duplicates goal/review state (it feeds review evidence; it
is not a review).
"""
from __future__ import annotations

from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.rbac.scope import actor_can_access, reporting_subtree_ids

from .models import CheckIn, CheckInPriority, ManagerResponse


def _valid_priorities(raw) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValidationError({"priorities": "Expected a list."})
    out = []
    for i, p in enumerate(raw):
        text = (p.get("text") if isinstance(p, dict) else "") or ""
        if not text.strip():
            continue
        status = (p.get("status") if isinstance(p, dict) else "") or CheckInPriority.Status.ACTIVE
        if status not in CheckInPriority.Status.values:
            raise ValidationError({"priorities": f"Invalid status {status!r}."})
        out.append({"text": text.strip()[:280], "status": status, "order": i})
    return out


def upsert_checkin(author, *, week_of, mood, wins="", blockers="", learning="", priorities=None):
    """Create or update ``author``'s own check-in for ``week_of`` (one per week).
    Replaces the priority list with the submitted set (the form sends the whole
    thing). Validates mood 1–5."""
    try:
        mood_i = int(mood)
    except (TypeError, ValueError):
        raise ValidationError({"mood": "Mood must be 1–5."})
    if not (1 <= mood_i <= 5):
        raise ValidationError({"mood": "Mood must be 1–5."})
    if not week_of:
        raise ValidationError({"week_of": "A week is required."})

    prios = _valid_priorities(priorities)
    check_in, _ = CheckIn.objects.update_or_create(
        author=author,
        week_of=week_of,
        defaults={
            "mood": mood_i,
            "wins": (wins or "").strip(),
            "blockers": (blockers or "").strip(),
            "learning": (learning or "").strip(),
        },
    )
    # Replace priorities with the submitted set. A queryset .delete() is a hard bulk
    # delete (priorities carry no history); status is how carry-forward is expressed.
    CheckInPriority.objects.filter(check_in=check_in).delete()
    for p in prios:
        CheckInPriority.objects.create(check_in=check_in, **p)
    return check_in


def my_checkins(author):
    """``author``'s own check-ins, newest first (priorities + response prefetched)."""
    return (
        CheckIn.objects.filter(author_id=author.id)
        .select_related("author", "response", "response__responder")
        .prefetch_related("priorities")
        .order_by("-week_of")
    )


def team_checkins(manager):
    """Check-ins authored by anyone in ``manager``'s reporting subtree (scope-bound;
    never the manager's own — those belong to THEIR manager). Tenant-scoped."""
    subtree = reporting_subtree_ids(manager)
    if not subtree:
        return CheckIn.objects.none()
    return (
        CheckIn.objects.filter(author_id__in=subtree)
        .select_related("author", "response", "response__responder")
        .prefetch_related("priorities")
        .order_by("-week_of")
    )


def get_readable_checkin(user, checkin_id):
    """Load a check-in ``user`` may read: their own, or (manager) one in their
    subtree. Anything else → 404 (never reveal it exists)."""
    ci = (
        CheckIn.objects.select_related("author", "response", "response__responder")
        .prefetch_related("priorities")
        .filter(id=checkin_id)
        .first()
    )
    if ci is None:
        raise NotFound("Check-in not found.")
    if ci.author_id == user.id:
        return ci
    if actor_can_access(user, ci.author):  # manager over a report
        return ci
    raise NotFound("Check-in not found.")


def respond_to_checkin(manager, checkin_id, *, comment="", reaction="", follow_up=False, add_to_one_on_one=False):
    """A manager responds to a REPORT's check-in (one response per check-in). The
    manager must be able to access the author and not be the author."""
    ci = CheckIn.objects.select_related("author").filter(id=checkin_id).first()
    if ci is None:
        raise NotFound("Check-in not found.")
    if ci.author_id == manager.id:
        raise PermissionDenied("You can't respond to your own check-in.")
    if not actor_can_access(manager, ci.author):
        raise NotFound("Check-in not found.")  # out of scope — don't reveal
    response, _ = ManagerResponse.objects.update_or_create(
        check_in=ci,
        defaults={
            "responder": manager,
            "comment": (comment or "").strip(),
            "reaction": (reaction or "").strip()[:8],
            "follow_up": bool(follow_up),
            "add_to_one_on_one": bool(add_to_one_on_one),
        },
    )
    return response


def checkin_goal_progress(author) -> list[dict]:
    """READ-ONLY pull of ``author``'s active goals with current KPI attainment —
    reuses the goals engine (``kpi_attainment``); stores/duplicates nothing."""
    from apps.goals.models import Goal
    from apps.goals.scoring.engine import kpi_attainment

    out = []
    goals = Goal.objects.filter(employee_id=author.id, status=Goal.Status.ACTIVE).prefetch_related("kpis")
    for g in goals:
        kpis = list(g.kpis.all())
        atts = [float(kpi_attainment(k)) for k in kpis]
        avg = round(sum(atts) / len(atts) * 100) if atts else None
        out.append({"goal": g.title, "attainment_pct": avg})
    return out
