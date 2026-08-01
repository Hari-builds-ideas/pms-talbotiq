"""
AI assistant ACTIONS — propose-and-confirm, human in the loop (RW_BUILD_4/5 + AGENTIC_CHAT).

The chat assistant may PROPOSE a supported action; **nothing happens until the human
acts** — either taps Approve (``feel="confirm"`` → :func:`execute_action`, the ONLY write
path) or opens the deep-linked screen (``feel="navigate"``) and completes it there via the
screen's own audited endpoint. Execute RE-CHECKS the caller's capability + data scope on the
REAL targets, calling the SAME service the human path uses — so the assistant can never do
what the user couldn't do via the normal endpoint, and a proposal is inert data.

THE INVARIANT (AGENTIC_CHAT_BUILD.md): the model PROPOSES/DRAFTS; the human APPROVES; the
endpoint EXECUTES with full server-side authz re-checked at execute time. Parameters are
resolved DETERMINISTICALLY here against ONLY what the caller can see (never model-extracted
permissions, never free text re-interpreted as a command) — so an instruction embedded in a
field is just data. Capability is checked at proposal AND re-checked at execution (execution
is authoritative). We never propose what the caller lacks capability/scope to do.
"""
from __future__ import annotations

import datetime
import re

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit.services import record as audit_record
from apps.ai.directory import AMBIGUOUS, resolve_person_in_population
from apps.rbac.matrix import Capability, role_has_capability
from apps.rbac.scope import Scope, actor_can_access, reporting_subtree_ids, scope_for_role

#: cap a single proposal/execution so a runaway can't approve an unbounded set.
_MAX_TARGETS = 50

#: :data:`AMBIGUOUS` (a name/role matched more than one target → the chat must ASK) is
#: the shared sentinel from :mod:`apps.ai.directory`, re-exported for the propose/
#: execute code below that compares ``result is AMBIGUOUS``.


def _display(user) -> str:
    return (getattr(user, "display_name", "") or "").strip() or "a teammate"


# ── scope-bound resolution (deterministic; only what the caller can see) ────────


def _visible_user_ids(user) -> set:
    """The user ids the caller may see — the SAME envelope their reads obey: TENANT
    for HRBP/Admin, their reporting subtree (+self) for a Manager, self for an
    Employee. Resolution NEVER ranges beyond this (out-of-scope == doesn't exist)."""
    from apps.identity.models import User

    scope = scope_for_role(user.role)
    if scope is Scope.TENANT:
        return set(User.objects.filter(is_active=True).values_list("id", flat=True))
    if scope is Scope.TEAM:
        return set(reporting_subtree_ids(user)) | {user.id}
    return {user.id}


def _resolve_person(user, message: str):
    """Resolve a person NAMED in the message for a DATA/write action — the directory
    lookup is restricted to the caller's VISIBLE scope, so an out-of-scope name simply
    doesn't resolve (treated as a 404; we never reveal an out-of-scope person exists).
    Tiered matching (exact full name wins, never disambiguates on a shared first name).
    Returns a User, ``None``, or :data:`AMBIGUOUS`. The action's own access check still
    runs before any data is read — resolution alone grants nothing."""
    vis = _visible_user_ids(user)
    if not vis:
        return None
    # exclude_self=False: the visible set already includes self, and some data actions
    # legitimately name the caller; the per-action scope/own-guard decides what's valid.
    return resolve_person_in_population(user, message, population_ids=vis, exclude_self=False)


def _resolve_critical_role(user, message: str):
    """Resolve a CriticalRole NAMED in the message within the caller's scope (the
    tenant-scoped manager already bounds tenant; succession capability bounds role).
    Returns the role, None, or AMBIGUOUS."""
    from apps.succession.models import CriticalRole

    m = (message or "").lower()
    hits = [r for r in CriticalRole.objects.filter(status=CriticalRole.Status.ACTIVE) if r.name and r.name.lower() in m]
    if not hits:
        return None
    if len(hits) > 1:
        return AMBIGUOUS
    return hits[0]


def _clarify(question: str, candidates=None) -> dict:
    """A non-executable proposal that just asks the user to disambiguate. ``candidates``
    (name + email) let the UI list who was meant so the user can pick — and the planner
    records which action to resume when the user answers (pending-slot follow-up)."""
    return {
        "action": "clarify", "feel": "clarify", "summary": question, "preview": [],
        "params": {}, "candidates": candidates or [],
    }


def _candidate_rows(users) -> list:
    """Name+email options for a disambiguation prompt (data only — no scores)."""
    return [{"id": str(u.id), "name": _display(u), "email": u.email} for u in users]


def _artifact(type_: str, id_, title: str, state: str, deeplink: str) -> dict:
    """The thing an executed action produced/touched, for a rich result card + a
    deep link (AGENT_UX_V3 §B). ``deeplink`` is a PLAIN client route that already
    exists in the SPA router (verified) — never an invented path. ``id_`` may be
    None for actions with no single artifact id."""
    return {
        "type": type_,
        "id": str(id_) if id_ is not None else None,
        "title": title,
        "state": state,
        "deeplink": deeplink,
    }


# ── approve_goals (RW_BUILD_4) ──────────────────────────────────────────────────


def _pending_goals_in_scope(user):
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
    if not role_has_capability(user.role, Capability.APPROVE_GOALS):
        return None
    goals = _pending_goals_in_scope(user)
    if not goals:
        return None
    return {
        "action": "approve_goals",
        "feel": "confirm",
        "summary": f"Approve {len(goals)} pending goal(s) for your team?",
        "preview": [{"goal": g.title, "employee": _display(g.employee)} for g in goals],
        "params": {"goal_ids": [str(g.id) for g in goals]},
    }


def _execute_approve_goals(user, params) -> dict:
    from apps.goals.models import Goal

    if not role_has_capability(user.role, Capability.APPROVE_GOALS):
        raise PermissionDenied("You don't have permission to approve goals.")
    ids = params.get("goal_ids") or []
    if not isinstance(ids, list):
        raise ValidationError({"goal_ids": "Expected a list."})
    approved, skipped, last_goal = 0, [], None
    for gid in ids[:_MAX_TARGETS]:
        goal = Goal.objects.filter(id=gid).select_related("employee").first()
        if goal is None:
            skipped.append({"goal_id": str(gid), "reason": "not_found"})
            continue
        if not actor_can_access(user, goal.employee):
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
        last_goal = goal
    out = {"action": "approve_goals", "approved": approved, "skipped": skipped}
    if last_goal is not None:  # deep-link to the (last) approved goal's owner profile
        out["artifact"] = _artifact(
            "goal", last_goal.id, f"Goal approved — {_display(last_goal.employee)}",
            "APPROVED", f"/people/{last_goal.employee_id}",
        )
    return out


# ── approve_reviews (RW_BUILD_5) ────────────────────────────────────────────────


def _pending_reviews_in_scope(user):
    from apps.reviews.models import Review

    subtree = reporting_subtree_ids(user)
    if not subtree:
        return []
    return list(
        Review.objects.filter(
            employee_id__in=subtree, state=Review.State.PENDING_HUMAN_REVIEW
        ).select_related("employee")[:_MAX_TARGETS]
    )


def _propose_approve_reviews(user, _message):
    if not role_has_capability(user.role, Capability.APPROVE_REVIEW):
        return None
    reviews = _pending_reviews_in_scope(user)
    if not reviews:
        return None
    return {
        "action": "approve_reviews",
        "feel": "confirm",
        "summary": f"Approve {len(reviews)} review(s) pending your sign-off?",
        "preview": [{"employee": _display(r.employee)} for r in reviews],
        "params": {"review_ids": [str(r.id) for r in reviews]},
    }


def _execute_approve_reviews(user, params) -> dict:
    from apps.reviews import state_machine
    from apps.reviews.models import Review

    if not role_has_capability(user.role, Capability.APPROVE_REVIEW):
        raise PermissionDenied("You don't have permission to approve reviews.")
    ids = params.get("review_ids") or []
    if not isinstance(ids, list):
        raise ValidationError({"review_ids": "Expected a list."})
    approved, skipped, last_review = 0, [], None
    for rid in ids[:_MAX_TARGETS]:
        review = Review.objects.filter(id=rid).select_related("employee").first()
        if review is None:
            skipped.append({"review_id": str(rid), "reason": "not_found"})
            continue
        try:
            state_machine.approve(review, user)
            approved += 1
            last_review = review
        except Exception as exc:  # noqa: BLE001 — out of scope / wrong state → skip, never force
            skipped.append({"review_id": str(rid), "reason": type(exc).__name__})
    out = {"action": "approve_reviews", "approved": approved, "skipped": skipped}
    if last_review is not None:
        out["artifact"] = _artifact(
            "review", last_review.id, f"Review approved — {_display(last_review.employee)}",
            "APPROVED", f"/reviews/{last_review.id}",
        )
    return out


# ── draft_review (AGENTIC_CHAT) — confirm → existing async Agent-1 seam ──────────
#     mirrors ReviewRequestAIDraftView: RUN_AI_REVIEW_DRAFT + actor_can_access(employee)
#     + enqueue agent1. No eligible DRAFT review → navigate-and-prefill create-review.


def _eligible_draft_reviews(user):
    from apps.reviews.models import Review

    ids = set(reporting_subtree_ids(user)) | {user.id}
    if not ids:
        return []
    return list(
        Review.objects.filter(employee_id__in=ids, state=Review.State.DRAFT)
        .select_related("employee")[:_MAX_TARGETS]
    )


def _propose_draft_review(user, message):
    if not role_has_capability(user.role, Capability.RUN_AI_REVIEW_DRAFT):
        return None
    person = _resolve_person(user, message)
    if person is AMBIGUOUS:
        return _clarify("Whose review should I draft? Please name one person.")
    candidates = _eligible_draft_reviews(user)
    if person is not None:
        candidates = [r for r in candidates if r.employee_id == person.id]
    if len(candidates) == 1:
        r = candidates[0]
        return {
            "action": "draft_review",
            "feel": "confirm",
            "summary": f"Draft an AI review for {_display(r.employee)}? You'll review and approve it before it's final.",
            "preview": [{"employee": _display(r.employee)}],
            "params": {"review_id": str(r.id)},
        }
    if len(candidates) > 1:
        return _clarify("You have several draft reviews — please name the person whose review I should draft.")
    # none eligible → navigate-and-prefill the Reviews screen (human creates it there)
    return {
        "action": "draft_review",
        "feel": "navigate",
        "summary": "No draft review to work from — open Reviews to create one, then ask me to draft it.",
        "preview": [],
        "deeplink": "/reviews",
        "prefill": {"employee": str(person.id) if person else ""},
    }


def _execute_draft_review(user, params) -> dict:
    from apps.ai.services import enqueue_agent_job
    from apps.reviews.models import Review

    if not role_has_capability(user.role, Capability.RUN_AI_REVIEW_DRAFT):
        raise PermissionDenied("You don't have permission to request AI review drafts.")
    review = Review.objects.filter(id=params.get("review_id")).select_related("employee").first()
    if review is None:
        raise ValidationError({"review_id": "No such review."})
    if not actor_can_access(user, review.employee):  # SAME object scope as the view
        raise PermissionDenied("That review is out of your scope.")
    job = enqueue_agent_job(actor=user, agent_code="agent1", target_type="review", target_id=review.id)
    return {
        "action": "draft_review",
        "ok": True,
        "job_id": str(job.id),
        "message": f"AI draft requested for {_display(review.employee)} — it'll land pending your review.",
        "artifact": _artifact(
            "review", review.id, f"Review — {_display(review.employee)}",
            "AI_DRAFTING", f"/reviews/{review.id}",
        ),
    }


# ── career_enrich (AGENTIC_CHAT) — confirm → existing async career seam ──────────
#     mirrors RoadmapEnrichView: MANAGE_CAREER_ROADMAP + get_roadmap_in_scope (404) + enqueue.


def _propose_career_enrich(user, message):
    if not role_has_capability(user.role, Capability.MANAGE_CAREER_ROADMAP):
        return None
    from apps.career.models import DevelopmentRoadmap

    person = _resolve_person(user, message)
    if person is AMBIGUOUS:
        return _clarify("Whose roadmap should I enrich? Please name one person.")
    target = person or user  # "enrich my roadmap" → self; "for <report>" → that report
    rm = (
        DevelopmentRoadmap.objects.filter(employee_id=target.id, status=DevelopmentRoadmap.Status.ACTIVE)
        .order_by("-created_at")
        .first()
    )
    if rm is None:
        return None  # no active roadmap → chat replies normally (nothing to enrich)
    whose = "your" if target.id == user.id else f"{_display(target)}'s"
    return {
        "action": "career_enrich",
        "feel": "confirm",
        "summary": f"Enrich {whose} development roadmap with AI? It lands as a draft you adopt.",
        "preview": [{"employee": _display(target)}],
        "params": {"roadmap_id": str(rm.id)},
    }


def _execute_career_enrich(user, params) -> dict:
    from apps.ai.services import enqueue_agent_job
    from apps.career import services

    if not role_has_capability(user.role, Capability.MANAGE_CAREER_ROADMAP):
        raise PermissionDenied("You don't have permission to enrich roadmaps.")
    roadmap = services.get_roadmap_in_scope(user, params.get("roadmap_id"))  # raises 404 out-of-scope
    job = enqueue_agent_job(actor=user, agent_code="career_roadmap", target_type="career_roadmap", target_id=roadmap.id)
    return {
        "action": "career_enrich",
        "ok": True,
        "job_id": str(job.id),
        "message": "Roadmap enrichment requested — adopt the AI draft when it's ready.",
        "artifact": _artifact("career_roadmap", roadmap.id, "Development roadmap", "ENRICHING", "/career"),
    }


# ── succession_enrich (AGENTIC_CHAT) — confirm → existing async Agent-4 seam ─────
#     mirrors PlanEnrichView: GENERATE_SUCCESSION_ANALYSIS (HRBP+) + get_plan_in_scope (404) +
#     enqueue agent4. Employees lack the capability → never proposed (succession stays a 404).


def _propose_succession_enrich(user, message):
    if not role_has_capability(user.role, Capability.GENERATE_SUCCESSION_ANALYSIS):
        return None  # employees never see succession
    role = _resolve_critical_role(user, message)
    if role is AMBIGUOUS:
        return _clarify("Which critical role's plan should I enrich? Please name the role.")
    if role is None:
        return None
    from apps.succession.models import SuccessionPlan

    plan = SuccessionPlan.objects.filter(critical_role=role).order_by("-generated_at").first()
    if plan is None:
        return _clarify(f"There's no plan for {role.name} yet — generate one on the Succession screen, then ask me to enrich it.")
    return {
        "action": "succession_enrich",
        "feel": "confirm",
        "summary": f"Enrich the succession plan for {role.name} with AI? It lands pending your review.",
        "preview": [{"role": role.name}],
        "params": {"plan_id": str(plan.id)},
    }


def _execute_succession_enrich(user, params) -> dict:
    from apps.ai.services import enqueue_agent_job
    from apps.succession import plans

    if not role_has_capability(user.role, Capability.GENERATE_SUCCESSION_ANALYSIS):
        raise PermissionDenied("You don't have permission to enrich succession plans.")
    plan = plans.get_plan_in_scope(user, params.get("plan_id"))  # raises 404 out-of-scope
    job = enqueue_agent_job(actor=user, agent_code="agent4", target_type="succession_plan", target_id=plan.id)
    return {
        "action": "succession_enrich",
        "ok": True,
        "job_id": str(job.id),
        "message": f"Succession enrichment requested for {plan.critical_role.name}.",
        "artifact": _artifact(
            "succession_plan", plan.id, f"Succession plan — {plan.critical_role.name}",
            "ENRICHING", "/succession",
        ),
    }


# ── initiate_360 (AGENTIC_CHAT) — confirm → existing cycle-create path ───────────
#     mirrors FeedbackCycleListCreateView.post: MANAGE_FEEDBACK_CYCLE + actor_can_access(subject)
#     + create DRAFT cycle (opened_by server-set). Reviewer invites stay a separate human step.


def _propose_initiate_360(user, message):
    if not role_has_capability(user.role, Capability.MANAGE_FEEDBACK_CYCLE):
        return None
    subject = _resolve_person(user, message)
    if subject is AMBIGUOUS:
        return _clarify("Who is the 360 for? Please name one person.")
    if subject is None:
        return {  # no clear subject → navigate-and-prefill the cycle screen
            "action": "initiate_360",
            "feel": "navigate",
            "summary": "Open the 360 screen to start a feedback cycle and choose the subject + reviewers.",
            "preview": [],
            "deeplink": "/feedback",
            "prefill": {"tab": "cycles"},
        }
    return {
        "action": "initiate_360",
        "feel": "confirm",
        "summary": f"Start a 360 feedback cycle for {_display(subject)}? You then invite the reviewers.",
        "preview": [{"employee": _display(subject)}],
        "params": {"subject_id": str(subject.id)},
    }


def _execute_initiate_360(user, params) -> dict:
    from apps.feedback.models import FeedbackCycle
    from apps.identity.models import User

    if not role_has_capability(user.role, Capability.MANAGE_FEEDBACK_CYCLE):
        raise PermissionDenied("You don't have permission to manage feedback cycles.")
    subject = User.objects.filter(id=params.get("subject_id")).first()  # tenant-scoped
    if subject is None:
        raise ValidationError({"subject_id": "No such person."})
    if not actor_can_access(user, subject):  # SAME scope-on-create check as the view
        raise PermissionDenied("That person is out of your scope.")
    cycle = FeedbackCycle.objects.create(
        tenant_id=user.tenant_id,
        subject=subject,
        opened_by=user,  # server-set, never client-supplied
        status=FeedbackCycle.Status.DRAFT,
    )
    audit_record(action="feedback_cycle.created", actor=user, target_type="feedback_cycle", target_id=cycle.id)
    return {
        "action": "initiate_360",
        "ok": True,
        "cycle_id": str(cycle.id),
        "message": f"360 cycle created for {_display(subject)} (draft) — open it to invite reviewers.",
        "artifact": _artifact(
            "feedback_cycle", cycle.id, f"360 — {_display(subject)}", "DRAFT", "/feedback",
        ),
    }


# ── create_jd (AGENTIC_CHAT) — navigate-and-prefill (many fields; human submits) ─
#     No chat write: deep-links the JD screen; the human fills + Generates via the audited
#     JD endpoints. The extracted title is PREFILL DATA only (never a command).


def _extract_jd_title(message: str) -> str:
    m = message or ""
    for marker in (" jd for ", " job description for ", " jd for a ", " role of "):
        i = m.lower().find(marker.strip() and marker)
        if i != -1:
            return m[i + len(marker):].strip().strip(".?!").strip()[:120]
    return ""


def _propose_create_jd(user, message):
    if not role_has_capability(user.role, Capability.MANAGE_JD_LIBRARY):
        return None
    title = _extract_jd_title(message)
    return {
        "action": "create_jd",
        "feel": "navigate",
        "summary": (f"Open the JD Library to create a JD for “{title}”" if title else "Open the JD Library to create a new JD")
        + " — you fill the details and Generate there.",
        "preview": [{"title": title}] if title else [],
        "deeplink": "/jd",
        "prefill": {"title": title},  # PREFILL DATA — the human reviews + submits via the JD endpoint
    }


# ── record_actual (OVERNIGHT_A) — confirm → mirrors KpiActualsView (OWN only) ────
#     UPDATE_OWN_ACTUALS + the KPI must belong to the CALLER (goal.employee_id == self,
#     exactly like the view — a manager can't use this path) + record_actual service +
#     the `actual.recorded` audit. Params (kpi + value) resolve deterministically from
#     the caller's OWN active KPIs; ambiguous / no number → the chat ASKS.

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _extract_number(message: str):
    m = _NUM_RE.search(message or "")
    return m.group(0) if m else None


def _own_active_kpis(user):
    from apps.goals.models import Goal, Kpi

    return list(
        Kpi.objects.filter(goal__employee_id=user.id, goal__status=Goal.Status.ACTIVE)
        .select_related("goal")[:_MAX_TARGETS]
    )


def _propose_record_actual(user, message):
    if not role_has_capability(user.role, Capability.UPDATE_OWN_ACTUALS):
        return None
    kpis = _own_active_kpis(user)
    if not kpis:
        return None  # nothing of the caller's own to record against → chat replies normally
    m = (message or "").lower()
    matched = [k for k in kpis if k.name and k.name.lower() in m]  # OWN KPIs only, by name
    value = _extract_number(message)
    if len(matched) != 1 or value is None:
        # never guess WHICH KPI or WHAT number — ask (deterministic-params rule).
        return _clarify("Which KPI, and what value? e.g. “record 85 for <KPI name>”.")
    k = matched[0]
    unit = f" {k.unit}" if k.unit else ""
    return {
        "action": "record_actual",
        "feel": "confirm",
        "summary": f"Record {value}{unit} for your KPI “{k.name}”? It updates your progress.",
        "preview": [{"kpi": k.name, "value": value}],
        "params": {"kpi_id": str(k.id), "value": value},
    }


def _execute_record_actual(user, params) -> dict:
    from decimal import Decimal, InvalidOperation

    from apps.goals.models import Kpi
    from apps.goals.services import record_actual as record_actual_svc

    if not role_has_capability(user.role, Capability.UPDATE_OWN_ACTUALS):
        raise PermissionDenied("You don't have permission to record actuals.")
    kpi = Kpi.objects.filter(id=params.get("kpi_id")).select_related("goal").first()
    if kpi is None:
        raise ValidationError({"kpi_id": "No such KPI."})
    # OWN-only — EXACTLY the KpiActualsView check (a manager must NOT pass here).
    if kpi.goal.employee_id != user.id:
        raise PermissionDenied("You can only record actuals on your own KPIs.")
    try:
        value = Decimal(str(params.get("value")))  # junk / injected text → rejected, no write
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({"value": "Enter a number."})
    audit_record(
        action="actual.recorded", actor=user, target_type="kpi", target_id=kpi.id,
        metadata={"value": str(value)},
    )
    measurement = record_actual_svc(kpi, value, recorded_by=user)  # SAME single write path
    return {
        "action": "record_actual", "ok": True, "measurement_id": str(measurement.id),
        "message": f"Recorded {value} for “{kpi.name}”.",
        "artifact": _artifact("kpi", kpi.id, f"{kpi.name} — {value}", "RECORDED", "/goals"),
    }


# ── give_recognition (OVERNIGHT_A) — confirm → mirrors create_recognition ────────
#     GIVE_RECOGNITION (everyone) + create_recognition service (recipient must be a
#     same-tenant active user, self-recognition blocked, value ∈ COMPANY_VALUES) +
#     the `recognition.created` audit. Recognition is TENANT-WIDE by design (anyone
#     recognises anyone in-tenant), so the recipient resolves across the tenant — but
#     tenant isolation still rides on the scoped manager (a cross-tenant name never
#     resolves). The note is DATA — stored verbatim, never parsed as a command.


def _resolve_recipient_in_tenant(user, message: str):
    """Resolve a recognition RECIPIENT named in the message. Recognition is a
    DIRECTORY-only action: you may recognise anyone in the company, so the search
    ranges over the WHOLE active tenant (``population_ids=None``), excluding self.
    Tiered matching means an exact full name ("Priya Nair") wins even when six other
    people share the first name "Priya" — it never collapses to a dead-end ASK.
    Tenant isolation still rides on the scoped manager (a cross-tenant name never
    resolves). Returns a User, ``None``, or :data:`AMBIGUOUS`."""
    return resolve_person_in_population(user, message, population_ids=None, exclude_self=True)


def _extract_company_value(message: str):
    from apps.recognition.models import COMPANY_VALUES

    m = (message or "").lower()
    for v in COMPANY_VALUES:
        if v.lower() in m:
            return v
    return None


def _propose_give_recognition(user, message):
    if not role_has_capability(user.role, Capability.GIVE_RECOGNITION):
        return None
    recipient = _resolve_recipient_in_tenant(user, message)
    if recipient is AMBIGUOUS:
        from apps.ai.directory import suggest_candidates

        options = suggest_candidates(user, message, population_ids=None, exclude_self=True)
        names = ", ".join(_display(u) for u in options[:6])
        q = (f"More than one colleague matches — did you mean {names}? "
             "Tell me their full name or email.") if names else \
            "Who would you like to recognise? Please name one colleague."
        return _clarify(q, candidates=_candidate_rows(options))
    if recipient is None:
        return _clarify("Who would you like to recognise, and what for? Name a colleague.")
    value = _extract_company_value(message) or "Teamwork"  # a default the human can change
    return {
        "action": "give_recognition",
        "feel": "confirm",
        "summary": f"Give {_display(recipient)} recognition for {value}? It posts to your team feed — edit the note first if you like.",
        "preview": [{"recipient": _display(recipient), "value": value}],
        "params": {
            "recipient_user_id": str(recipient.id),
            "category": value,
            "note": f"Recognised for {value}.",  # a clean default note; the human edits/approves
        },
    }


def _execute_give_recognition(user, params) -> dict:
    from apps.recognition.services import create_recognition

    if not role_has_capability(user.role, Capability.GIVE_RECOGNITION):
        raise PermissionDenied("You don't have permission to give recognition.")
    # create_recognition validates value/visibility/message, blocks self, resolves the
    # recipient tenant-scoped (cross-tenant → NotFound), and audits `recognition.created`.
    rec = create_recognition(
        user,
        recipient_id=params.get("recipient_user_id"),
        value=params.get("category") or "",
        message=params.get("note") or "",  # DATA — stored verbatim, never a command
        visibility="TEAM",
    )
    return {
        "action": "give_recognition", "ok": True, "recognition_id": str(rec.id),
        "message": f"Recognition posted for {_display(rec.recipient)}.",
        "artifact": _artifact(
            "recognition", rec.id, f"Recognition — {_display(rec.recipient)}", "POSTED", "/recognition",
        ),
    }


# ══ OVERNIGHT_F — agent actions expansion ═══════════════════════════════════════
# Each new action reuses the SAME audited service a human calls and re-checks
# capability + scope at execute. No new gate, no widened permission.


# ── open_checkin (Employee+) — confirm → mirrors upsert_checkin (OWN check-in) ───
#     MANAGE_OWN_CHECKIN (everyone) + upsert_checkin for the CALLER's OWN weekly
#     check-in. Non-destructive: an existing week's check-in is never clobbered
#     (upsert replaces its priorities) — we navigate to it instead. Mood is REAL
#     data the caller states (1–5); no mood → the chat ASKS (never invent a mood).

_MOOD_WORDS = {
    "struggling": 1, "awful": 1, "terrible": 1, "burnt out": 1, "burned out": 1,
    "rough": 2, "tough": 2, "stressed": 2, "drained": 2, "tired": 2,
    "ok": 3, "okay": 3, "fine": 3, "meh": 3, "average": 3, "alright": 3,
    "good": 4, "solid": 4, "productive": 4,
    "great": 5, "excellent": 5, "amazing": 5, "fantastic": 5,
}


def _current_week_monday() -> datetime.date:
    today = timezone.now().date()
    return today - datetime.timedelta(days=today.weekday())


def _extract_mood(message: str):
    """A mood 1–5 the caller STATED — "mood 4", "4/5", or a mood word. Returns an
    int or None (None → the chat asks; we never fabricate a mood)."""
    m = (message or "").lower()
    hit = re.search(r"\bmood\s*(?:of|is|=|:)?\s*([1-5])\b", m) or re.search(r"\b([1-5])\s*/\s*5\b", m)
    if hit:
        return int(hit.group(1))
    for word, val in _MOOD_WORDS.items():
        if word in m:
            return val
    return None


def _propose_open_checkin(user, message):
    from apps.checkins.models import CheckIn

    if not role_has_capability(user.role, Capability.MANAGE_OWN_CHECKIN):
        return None
    week = _current_week_monday()
    if CheckIn.objects.filter(author_id=user.id, week_of=week).exists():
        # never clobber an existing week (upsert replaces priorities) — go open it.
        return {
            "action": "open_checkin", "feel": "navigate",
            "summary": "You already have this week's check-in — open Check-ins to update it.",
            "preview": [], "deeplink": "/checkins", "prefill": {},
        }
    mood = _extract_mood(message)
    if mood is None:
        return _clarify("How are you feeling this week (1–5)? e.g. “start my check-in, mood 4”.")
    return {
        "action": "open_checkin", "feel": "confirm",
        "summary": f"Start this week's check-in with mood {mood}/5? You can add wins & blockers next.",
        "preview": [{"week_of": week.isoformat(), "mood": mood}],
        "params": {"week_of": week.isoformat(), "mood": mood},
    }


def _execute_open_checkin(user, params) -> dict:
    from apps.checkins.models import CheckIn
    from apps.checkins.services import upsert_checkin

    if not role_has_capability(user.role, Capability.MANAGE_OWN_CHECKIN):
        raise PermissionDenied("You don't have permission to manage your check-in.")
    try:
        week = datetime.date.fromisoformat(str(params.get("week_of")))
    except (ValueError, TypeError):
        raise ValidationError({"week_of": "Invalid week."})
    # Non-destructive + idempotent: never overwrite an existing week's check-in.
    existing = CheckIn.objects.filter(author_id=user.id, week_of=week).first()
    if existing is not None:
        return {"action": "open_checkin", "ok": True, "checkin_id": str(existing.id),
                "created": False, "message": "This week's check-in is already open.",
                "artifact": _artifact("checkin", existing.id, "This week's check-in", "OPEN", "/checkins")}
    ci = upsert_checkin(user, week_of=week, mood=params.get("mood"))  # service validates mood 1–5
    audit_record(action="checkin.opened", actor=user, target_type="checkin", target_id=ci.id,
                 metadata={"week_of": week.isoformat()})
    return {"action": "open_checkin", "ok": True, "checkin_id": str(ci.id),
            "created": True, "message": f"Opened your check-in for the week of {week.isoformat()}.",
            "artifact": _artifact("checkin", ci.id, "This week's check-in", "OPEN", "/checkins")}


# ── respond_to_checkin (Manager+) — confirm → mirrors respond_to_checkin svc ─────
#     RESPOND_CHECKIN (Manager+) + the report must be in the caller's scope (the
#     service 404s out-of-scope, 403s the caller's own). The report is resolved by
#     name within scope; the comment is a clean default the human approves (DATA).


def _propose_respond_checkin(user, message):
    from apps.checkins.models import CheckIn

    if not role_has_capability(user.role, Capability.RESPOND_CHECKIN):
        return None
    person = _resolve_person(user, message)
    if person is AMBIGUOUS:
        return _clarify("Whose check-in should I respond to? Please name one of your reports.")
    if person is None or person.id == user.id:
        return _clarify("Whose check-in should I respond to? Name one of your reports.")
    ci = CheckIn.objects.filter(author_id=person.id).order_by("-week_of").first()
    if ci is None:
        return None  # no check-in from them yet → chat replies normally
    return {
        "action": "respond_to_checkin", "feel": "confirm",
        "summary": f"Post a response to {_display(person)}'s check-in (week of {ci.week_of.isoformat()})?",
        "preview": [{"employee": _display(person), "week_of": ci.week_of.isoformat()}],
        "params": {"checkin_id": str(ci.id),
                   "comment": "Thanks for the update — noted. Let's talk through the blockers at our next 1:1."},
    }


def _execute_respond_checkin(user, params) -> dict:
    from apps.checkins.services import respond_to_checkin as respond_svc

    if not role_has_capability(user.role, Capability.RESPOND_CHECKIN):
        raise PermissionDenied("You don't have permission to respond to check-ins.")
    resp = respond_svc(user, params.get("checkin_id"), comment=params.get("comment") or "")
    audit_record(action="checkin.responded", actor=user, target_type="checkin", target_id=resp.check_in_id)
    return {"action": "respond_to_checkin", "ok": True, "response_id": str(resp.id),
            "message": "Response posted to the check-in.",
            "artifact": _artifact("checkin", resp.check_in_id, "Check-in response", "RESPONDED", "/checkins")}


# ── approve_goal (Manager+) — confirm → the singular sibling of approve_goals ─────
#     APPROVE_GOALS (Manager+) + the goal's employee in the caller's scope. Resolves
#     ONE named report's pending goal and approves just that one, reusing the SAME
#     audited approve path + execute-time scope re-check. Out-of-scope / cross-tenant
#     goal ids are skipped at execute (never approved).


def _propose_approve_goal(user, message):
    from apps.goals.models import Goal

    if not role_has_capability(user.role, Capability.APPROVE_GOALS):
        return None
    person = _resolve_person(user, message)
    if person is AMBIGUOUS:
        return _clarify("Whose goal should I approve? Please name one person.")
    subtree = reporting_subtree_ids(user)
    if not subtree:
        return None
    qs = Goal.objects.filter(
        employee_id__in=subtree, status=Goal.Status.ACTIVE, approved_by__isnull=True
    ).select_related("employee")
    if person is not None:
        qs = qs.filter(employee_id=person.id)
    pending = list(qs[:_MAX_TARGETS])
    if not pending:
        return None  # nothing pending in scope → chat replies normally
    if len(pending) > 1:
        if person is None:
            return _clarify("Which goal should I approve? Name the person whose goal it is.")
        # a named person with several pending goals — approve the most recent one.
        pending = pending[:1]
    g = pending[0]
    return {
        "action": "approve_goal", "feel": "confirm",
        "summary": f"Approve {_display(g.employee)}'s goal “{g.title}”?",
        "preview": [{"employee": _display(g.employee), "goal": g.title}],
        "params": {"goal_ids": [str(g.id)]},  # reuses the approve_goals execute path
    }


# ── schedule_review (Manager+) — navigate-and-prefill (no chat write) ────────────
#     MANAGE_REVIEWS (Manager+). Deep-links Reviews with the employee + current
#     cycle prefilled; the human creates + starts it there via the audited endpoint.
#     (The app hosts review creation on the Reviews list — there is no separate
#     "/reviews/new" route — so the deeplink is "/reviews".)


def _active_cycle_for(user):
    from apps.cycles.models import PerformanceCycle

    return (
        PerformanceCycle.objects.filter(status=PerformanceCycle.Status.ACTIVE)
        .order_by("-start_date")
        .first()
    )


def _propose_schedule_review(user, message):
    if not role_has_capability(user.role, Capability.MANAGE_REVIEWS):
        return None
    person = _resolve_person(user, message)
    if person is AMBIGUOUS:
        return _clarify("Whose review should I schedule? Please name one person.")
    cycle = _active_cycle_for(user)
    prefill = {}
    if person is not None:
        prefill["employee"] = str(person.id)
    if cycle is not None:
        prefill["cycle"] = str(cycle.id)
    who = _display(person) if person is not None else "someone on your team"
    return {
        "action": "schedule_review", "feel": "navigate",
        "summary": (f"Open Reviews to schedule a review for {who}"
                    + (" for the current cycle" if cycle is not None else "")
                    + " — you set it up and start it there."),
        "preview": [{"employee": who}] if person is not None else [],
        "deeplink": "/reviews", "prefill": prefill,
    }


# ── update_kpi_actual (Owner) — confirm → record_actual + suspicious-value warn ──
#     UPDATE_OWN_ACTUALS + the KPI must be the CALLER's own (mirrors record_actual /
#     KpiActualsView — a stricter sibling that WARNS on a value that contradicts the
#     target's direction or is a >50% jump, but still just RECORDS: no analysis
#     writes and NO widened scope — never a report's KPI).


def _direction_warning(kpi, value) -> list[str]:
    """Advisory warnings composed from the KPI's own facts — never blocks a record."""
    from decimal import Decimal, InvalidOperation

    warnings: list[str] = []
    try:
        val = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return warnings
    latest = kpi.measurements.first()  # ordered -recorded_at
    if latest is None:
        return warnings
    if latest.value != 0:
        delta = abs(val - latest.value) / abs(latest.value)
        if delta > Decimal("0.5"):
            warnings.append(f"that's a {round(float(delta) * 100)}% change from the last recorded {latest.value}")
    if kpi.direction == kpi.Direction.INCREASING and val < latest.value:
        warnings.append("this lowers a higher-is-better KPI")
    elif kpi.direction == kpi.Direction.DECREASING and val > latest.value:
        warnings.append("this raises a lower-is-better KPI")
    return warnings


def _propose_update_kpi_actual(user, message):
    if not role_has_capability(user.role, Capability.UPDATE_OWN_ACTUALS):
        return None
    kpis = _own_active_kpis(user)
    if not kpis:
        return None
    m = (message or "").lower()
    matched = [k for k in kpis if k.name and k.name.lower() in m]  # OWN KPIs only, by name
    value = _extract_number(message)
    if len(matched) != 1 or value is None:
        return _clarify("Which KPI, and what value? e.g. “update my Uptime KPI to 99”.")
    k = matched[0]
    warns = _direction_warning(k, value)
    warn_txt = (" ⚠️ " + "; ".join(warns) + ".") if warns else ""
    unit = f" {k.unit}" if k.unit else ""
    return {
        "action": "update_kpi_actual", "feel": "confirm",
        "summary": f"Update your KPI “{k.name}” to {value}{unit}?{warn_txt}",
        "preview": [{"kpi": k.name, "value": value, "warnings": warns}],
        "params": {"kpi_id": str(k.id), "value": value},
    }


def _execute_update_kpi_actual(user, params) -> dict:
    # SAME write + OWN-only guard as record_actual (never widens scope); the extra
    # validation is advisory at propose time. Reuse the single audited record path.
    result = _execute_record_actual(user, params)
    result["action"] = "update_kpi_actual"
    return result


# ── registry ──────────────────────────────────────────────────────────────────
# Order matters: the first match wins. Specific matches precede general ones. Each
# entry declares its `feel`; confirm actions have an `execute`, navigate actions do
# not (they're completed on the deep-linked screen).

ACTIONS: dict[str, dict] = {
    # approve_goal (singular) MUST precede approve_goals (bulk): "goals" not in the
    # message routes to the singular, named-person approve; "goals" to the bulk one.
    "approve_goal": {
        "feel": "confirm",
        "propose": _propose_approve_goal,
        "execute": _execute_approve_goals,  # same audited approve path, one goal id
        "capability": Capability.APPROVE_GOALS,
        "label": "approve a goal",
        "description": "Approve one named report's pending goal from your inbox.",
        "match": lambda m: "approve" in m and "goal" in m and "goals" not in m,
    },
    "approve_goals": {
        "feel": "confirm",
        "propose": _propose_approve_goals,
        "execute": _execute_approve_goals,
        "capability": Capability.APPROVE_GOALS,
        "label": "approve goals",
        "description": "Approve all pending goals across your team at once.",
        "match": lambda m: "approve" in m and "goal" in m,
    },
    "approve_reviews": {
        "feel": "confirm",
        "propose": _propose_approve_reviews,
        "execute": _execute_approve_reviews,
        "capability": Capability.APPROVE_REVIEW,
        "label": "approve reviews",
        "description": "Approve reviews pending your sign-off.",
        "match": lambda m: "approve" in m and "review" in m,
    },
    "draft_review": {
        "feel": "confirm",  # may downgrade to navigate inside propose when nothing is eligible
        "propose": _propose_draft_review,
        "execute": _execute_draft_review,
        "capability": Capability.RUN_AI_REVIEW_DRAFT,
        "label": "draft a review",
        "description": "Request an AI first draft of a team member's review (lands pending your approval).",
        "match": lambda m: "review" in m and ("draft" in m or "create" in m or "write" in m) and "approve" not in m and "360" not in m and "schedule" not in m,
    },
    "schedule_review": {
        "feel": "navigate",
        "propose": _propose_schedule_review,
        # no execute — navigate-and-prefill; the human creates + starts it on Reviews
        "capability": Capability.MANAGE_REVIEWS,
        "label": "schedule a review",
        "description": "Open Reviews with an employee + current cycle prefilled to schedule a review.",
        "match": lambda m: "schedule" in m and "review" in m,
    },
    "career_enrich": {
        "feel": "confirm",
        "propose": _propose_career_enrich,
        "execute": _execute_career_enrich,
        "capability": Capability.MANAGE_CAREER_ROADMAP,
        "label": "enrich a development roadmap",
        "description": "Enrich a development roadmap with AI (lands as an adoptable draft).",
        "match": lambda m: "enrich" in m and ("roadmap" in m or "career" in m),
    },
    "succession_enrich": {
        "feel": "confirm",
        "propose": _propose_succession_enrich,
        "execute": _execute_succession_enrich,
        "capability": Capability.GENERATE_SUCCESSION_ANALYSIS,
        # SENSITIVE: never name succession in a refusal — an employee must not learn it
        # exists (succession stays a 404 for them). Falls back to the generic refusal.
        "sensitive": True,
        "label": "enrich a succession plan",
        "description": "Enrich a critical-role succession plan with AI (pending your review).",
        "match": lambda m: "enrich" in m and ("succession" in m or "plan" in m),
    },
    "initiate_360": {
        "feel": "confirm",  # may downgrade to navigate inside propose when the subject is unclear
        "propose": _propose_initiate_360,
        "execute": _execute_initiate_360,
        "capability": Capability.MANAGE_FEEDBACK_CYCLE,
        "label": "start a 360",
        "description": "Start a 360 feedback cycle for a team member (you then invite reviewers).",
        "match": lambda m: "360" in m,
    },
    "create_jd": {
        "feel": "navigate",
        "propose": _propose_create_jd,
        # no execute — navigate-and-prefill; the human submits via the JD endpoint
        "capability": Capability.MANAGE_JD_LIBRARY,
        "label": "create a JD",
        "description": "Open the JD Library to create a job description.",
        "match": lambda m: ("jd" in m or "job description" in m),
    },
    "record_actual": {
        "feel": "confirm",
        "propose": _propose_record_actual,
        "execute": _execute_record_actual,
        "capability": Capability.UPDATE_OWN_ACTUALS,
        "label": "record a KPI actual",
        "description": "Record a new actual value on one of your own KPIs.",
        "match": lambda m: "record" in m
        and ("actual" in m or "kpi" in m or "progress" in m or any(c.isdigit() for c in m)),
    },
    "update_kpi_actual": {
        "feel": "confirm",
        "propose": _propose_update_kpi_actual,
        "execute": _execute_update_kpi_actual,
        "capability": Capability.UPDATE_OWN_ACTUALS,
        "label": "update a KPI actual",
        "description": "Update one of your own KPIs, with a warning if the value looks suspicious.",
        "match": lambda m: "update" in m and ("kpi" in m or "actual" in m) and any(c.isdigit() for c in m),
    },
    "give_recognition": {
        "feel": "confirm",
        "propose": _propose_give_recognition,
        "execute": _execute_give_recognition,
        "capability": Capability.GIVE_RECOGNITION,
        "label": "give recognition",
        "description": "Give a colleague recognition for a company value.",
        "match": lambda m: ("recogni" in m or "kudos" in m) and "approve" not in m,
    },
    # respond_to_checkin MUST precede open_checkin: "respond" routes to the manager
    # response; anything else about a check-in routes to opening the caller's own.
    "respond_to_checkin": {
        "feel": "confirm",
        "propose": _propose_respond_checkin,
        "execute": _execute_respond_checkin,
        "capability": Capability.RESPOND_CHECKIN,
        "label": "respond to a check-in",
        "description": "Post your response to a direct report's weekly check-in.",
        "match": lambda m: "respond" in m and ("checkin" in m or "check-in" in m or "check in" in m),
    },
    "open_checkin": {
        "feel": "confirm",  # may downgrade to navigate inside propose when one already exists
        "propose": _propose_open_checkin,
        "execute": _execute_open_checkin,
        "capability": Capability.MANAGE_OWN_CHECKIN,
        "label": "open your check-in",
        "description": "Start this week's check-in for yourself with a mood.",
        "match": lambda m: ("checkin" in m or "check-in" in m or "check in" in m) and "respond" not in m,
    },
}


def propose_action(user, message: str):
    """If the (write-intent) message matches a supported action the user is allowed
    to perform, return a proposal dict; else None (chat falls back to its refusal).
    A proposal may carry feel="confirm" (Approve → execute), "navigate" (open a
    deep-linked screen) or "clarify" (ask the user to disambiguate)."""
    m = (message or "").lower()
    for spec in ACTIONS.values():
        if spec["match"](m):
            return spec["propose"](user, message)
    return None


def write_refusal(user, message: str) -> str:
    """A PRECISE message when a write-intent query yields no proposal — so a capable
    user isn't fobbed off with a blanket "read-only" line (the misrouting bug). Returns:
      * a CAPABILITY refusal when the message matched a known action the caller can't
        perform (e.g. a manager asking for a JD — that's HRBP+), naming the action —
        EXCEPT for ``sensitive`` actions (succession), which never reveal they exist;
      * a "what would you like" ASK when nothing was recognised (a vague follow-up like
        "now make the draft" — we ask rather than guess the prior turn's context);
      * "" when an action matched and the caller IS capable but there was nothing to act
        on (e.g. no eligible review) — the caller's normal/gentle reply stands.
    """
    m = (message or "").lower()
    for spec in ACTIONS.values():
        if spec["match"](m):
            cap = spec.get("capability")
            if cap is not None and not role_has_capability(user.role, cap):
                if spec.get("sensitive"):
                    return ""  # don't name it — falls back to the generic refusal
                return (
                    f"You don't have permission to {spec['label']} — that's reserved for a "
                    "higher role here, so I can't propose it."
                )
            return ""  # recognised + capable, just nothing actionable right now
    return (
        "I can help you start a 360, draft a review, enrich a roadmap or succession plan, "
        "or create a JD — tell me which, and who or what it's for."
    )


def execute_action(user, action: str, params: dict) -> dict:
    """Run a previously proposed CONFIRM action — capability + scope re-checked inside.
    The ONLY write path; only ever reached on an explicit human Approve tap. Navigate /
    clarify actions are NOT executable from chat (they're completed on their screen)."""
    spec = ACTIONS.get(action)
    if spec is None or "execute" not in spec:
        raise ValidationError({"action": f"{action!r} can't be executed from chat — complete it on its screen."})
    return spec["execute"](user, params or {})


def describe_actions(user) -> list[dict]:
    """Public metadata for the actions surface (``GET /api/ai/actions/schema``):
    per action ``{name, label, description, feel, capability, allowed}`` — powering
    the assistant's "what can you do" list. A SENSITIVE action the caller can't
    perform is OMITTED (never reveal it exists — succession stays a 404 for an
    employee); everything else carries an ``allowed`` flag for the caller's role.
    Only what a caller could already infer by trying each action; no internals."""
    out: list[dict] = []
    for name, spec in ACTIONS.items():
        cap = spec.get("capability")
        allowed = cap is None or role_has_capability(user.role, cap)
        if spec.get("sensitive") and not allowed:
            continue
        out.append({
            "name": name,
            "label": spec.get("label", name),
            "description": spec.get("description", ""),
            "feel": spec.get("feel", "confirm"),
            # Capability members are plain strings; getattr keeps it safe either way.
            "capability": getattr(cap, "value", cap) if cap is not None else None,
            "allowed": allowed,
        })
    return out
