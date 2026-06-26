"""
AI assistant ACTIONS (RW_BUILD_4) — propose-and-confirm, human in the loop.

The chat assistant may PROPOSE a supported action; **nothing happens until the human
taps Approve**, which calls :func:`execute_action`. Execute is the only thing that
writes, and it RE-CHECKS the caller's capability + data scope on the REAL targets — so
the assistant can never do what the user couldn't do via the normal endpoint. Each
effect is audited exactly as the human endpoint audits it. A proposal is inert data.

Start small + safe: one action (`approve_goals`) that mirrors ``GoalApproveView``
exactly (APPROVE_GOALS + ``actor_can_access`` object scope + the ``goal.approved``
audit + the same stamp). The registry is built to take more actions later (D34).
"""
from __future__ import annotations

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit.services import record as audit_record
from apps.rbac.matrix import Capability, role_has_capability
from apps.rbac.scope import actor_can_access, reporting_subtree_ids

#: cap a single proposal/execution so a runaway can't approve an unbounded set.
_MAX_TARGETS = 50


def _display(user) -> str:
    return (getattr(user, "display_name", "") or "").strip() or "a teammate"


# ── approve_goals ─────────────────────────────────────────────────────────────


def _pending_goals_in_scope(user):
    """The unapproved ACTIVE goals the user could approve (their reporting subtree).
    Tenant-scoped by the manager; bounded."""
    from apps.goals.models import Goal

    subtree = reporting_subtree_ids(user)
    if not subtree:
        return []
    return list(
        Goal.objects.filter(
            employee_id__in=subtree, status=Goal.Status.ACTIVE, approved_by__isnull=True
        ).select_related("employee")[:_MAX_TARGETS]
    )


def _propose_approve_goals(user, _message):
    # Never propose what the user couldn't do: require the capability up front.
    if not role_has_capability(user.role, Capability.APPROVE_GOALS):
        return None
    goals = _pending_goals_in_scope(user)
    if not goals:
        return None  # nothing pending → don't propose; chat gives a normal reply
    return {
        "action": "approve_goals",
        "summary": f"Approve {len(goals)} pending goal(s) for your team?",
        "preview": [
            {"goal": g.title, "employee": _display(g.employee)} for g in goals
        ],
        "params": {"goal_ids": [str(g.id) for g in goals]},
    }


def _execute_approve_goals(user, params) -> dict:
    """Approve each goal — re-checking capability + object scope on EVERY target,
    exactly like ``GoalApproveView`` (which is the human path). Skips anything out of
    scope / already approved / missing; audits each approval before the side effect."""
    from apps.goals.models import Goal

    if not role_has_capability(user.role, Capability.APPROVE_GOALS):
        raise PermissionDenied("You don't have permission to approve goals.")
    ids = params.get("goal_ids") or []
    if not isinstance(ids, list):
        raise ValidationError({"goal_ids": "Expected a list."})
    approved, skipped = 0, []
    for gid in ids[:_MAX_TARGETS]:
        goal = Goal.objects.filter(id=gid).select_related("employee").first()  # tenant-scoped
        if goal is None:
            skipped.append({"goal_id": str(gid), "reason": "not_found"})
            continue
        if not actor_can_access(user, goal.employee):  # SAME object scope as the view
            skipped.append({"goal_id": str(gid), "reason": "out_of_scope"})
            continue
        if goal.approved_by_id is not None:
            skipped.append({"goal_id": str(gid), "reason": "already_approved"})
            continue
        audit_record(action="goal.approved", actor=user, target_type="goal", target_id=goal.id)
        goal.approved_by = user
        goal.approved_at = timezone.now()
        goal.save()
        approved += 1
    return {"action": "approve_goals", "approved": approved, "skipped": skipped}


# ── registry ──────────────────────────────────────────────────────────────────

ACTIONS: dict[str, dict] = {
    "approve_goals": {
        "propose": _propose_approve_goals,
        "execute": _execute_approve_goals,
        # Deterministic match on the (raw) message — the LLM decides it's a WRITE
        # intent; the action mapping stays deterministic + safe (D34).
        "match": lambda m: "approve" in m and "goal" in m,
    },
}


def propose_action(user, message: str):
    """If the (write-intent) message matches a supported action the user is allowed
    to perform, return a proposal dict; else None (chat falls back to its refusal)."""
    m = (message or "").lower()
    for spec in ACTIONS.values():
        if spec["match"](m):
            return spec["propose"](user, message)
    return None


def execute_action(user, action: str, params: dict) -> dict:
    """Run a previously proposed action — capability + scope re-checked inside.
    The ONLY write path; only ever reached on an explicit human Approve tap."""
    spec = ACTIONS.get(action)
    if spec is None:
        raise ValidationError({"action": f"Unknown action {action!r}."})
    return spec["execute"](user, params or {})
