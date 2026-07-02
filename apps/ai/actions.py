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

import re

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit.services import record as audit_record
from apps.rbac.matrix import Capability, role_has_capability
from apps.rbac.scope import Scope, actor_can_access, reporting_subtree_ids, scope_for_role

#: cap a single proposal/execution so a runaway can't approve an unbounded set.
_MAX_TARGETS = 50

#: sentinel: a name/role matched more than one in-scope target → the chat must ASK.
AMBIGUOUS = object()


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
    """Resolve a person NAMED in the message, but ONLY within the caller's visible
    scope. Returns a User, ``None`` (no in-scope match — treated as a 404; we never
    reveal an out-of-scope person exists), or :data:`AMBIGUOUS` (the chat asks)."""
    from apps.identity.models import User

    m = (message or "").lower()
    vis = _visible_user_ids(user)
    if not vis:
        return None
    hits = []
    for u in User.objects.filter(id__in=vis):
        name = (u.display_name or "").strip().lower()
        if not name:
            continue
        first = name.split()[0]
        if name in m or (len(first) >= 3 and re.search(rf"\b{re.escape(first)}\b", m)):
            hits.append(u)
    if not hits:
        return None
    if len(hits) > 1:
        return AMBIGUOUS
    return hits[0]


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


def _clarify(question: str) -> dict:
    """A non-executable proposal that just asks the user to disambiguate."""
    return {"action": "clarify", "feel": "clarify", "summary": question, "preview": [], "params": {}}


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
    approved, skipped = 0, []
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
    return {"action": "approve_goals", "approved": approved, "skipped": skipped}


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
    approved, skipped = 0, []
    for rid in ids[:_MAX_TARGETS]:
        review = Review.objects.filter(id=rid).select_related("employee").first()
        if review is None:
            skipped.append({"review_id": str(rid), "reason": "not_found"})
            continue
        try:
            state_machine.approve(review, user)
            approved += 1
        except Exception as exc:  # noqa: BLE001 — out of scope / wrong state → skip, never force
            skipped.append({"review_id": str(rid), "reason": type(exc).__name__})
    return {"action": "approve_reviews", "approved": approved, "skipped": skipped}


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
    }


# ── give_recognition (OVERNIGHT_A) — confirm → mirrors create_recognition ────────
#     GIVE_RECOGNITION (everyone) + create_recognition service (recipient must be a
#     same-tenant active user, self-recognition blocked, value ∈ COMPANY_VALUES) +
#     the `recognition.created` audit. Recognition is TENANT-WIDE by design (anyone
#     recognises anyone in-tenant), so the recipient resolves across the tenant — but
#     tenant isolation still rides on the scoped manager (a cross-tenant name never
#     resolves). The note is DATA — stored verbatim, never parsed as a command.


def _resolve_recipient_in_tenant(user, message: str):
    """Resolve a recognition RECIPIENT named in the message within the caller's
    TENANT (recognition's real scope), excluding self. Returns a User, ``None`` or
    :data:`AMBIGUOUS`. Tenant-scoped manager bounds it to the caller's tenant."""
    from apps.identity.models import User

    m = (message or "").lower()
    hits = []
    for u in User.objects.filter(is_active=True).exclude(id=user.id):
        name = (u.display_name or "").strip().lower()
        if not name:
            continue
        first = name.split()[0]
        if name in m or (len(first) >= 3 and re.search(rf"\b{re.escape(first)}\b", m)):
            hits.append(u)
    if not hits:
        return None
    if len(hits) > 1:
        return AMBIGUOUS
    return hits[0]


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
        return _clarify("Who would you like to recognise? Please name one colleague.")
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
    }


# ── registry ──────────────────────────────────────────────────────────────────
# Order matters: the first match wins. Specific matches precede general ones. Each
# entry declares its `feel`; confirm actions have an `execute`, navigate actions do
# not (they're completed on the deep-linked screen).

ACTIONS: dict[str, dict] = {
    "approve_goals": {
        "feel": "confirm",
        "propose": _propose_approve_goals,
        "execute": _execute_approve_goals,
        "capability": Capability.APPROVE_GOALS,
        "label": "approve goals",
        "match": lambda m: "approve" in m and "goal" in m,
    },
    "approve_reviews": {
        "feel": "confirm",
        "propose": _propose_approve_reviews,
        "execute": _execute_approve_reviews,
        "capability": Capability.APPROVE_REVIEW,
        "label": "approve reviews",
        "match": lambda m: "approve" in m and "review" in m,
    },
    "draft_review": {
        "feel": "confirm",  # may downgrade to navigate inside propose when nothing is eligible
        "propose": _propose_draft_review,
        "execute": _execute_draft_review,
        "capability": Capability.RUN_AI_REVIEW_DRAFT,
        "label": "draft a review",
        "match": lambda m: "review" in m and ("draft" in m or "create" in m or "write" in m) and "approve" not in m and "360" not in m,
    },
    "career_enrich": {
        "feel": "confirm",
        "propose": _propose_career_enrich,
        "execute": _execute_career_enrich,
        "capability": Capability.MANAGE_CAREER_ROADMAP,
        "label": "enrich a development roadmap",
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
        "match": lambda m: "enrich" in m and ("succession" in m or "plan" in m),
    },
    "initiate_360": {
        "feel": "confirm",  # may downgrade to navigate inside propose when the subject is unclear
        "propose": _propose_initiate_360,
        "execute": _execute_initiate_360,
        "capability": Capability.MANAGE_FEEDBACK_CYCLE,
        "label": "start a 360",
        "match": lambda m: "360" in m,
    },
    "create_jd": {
        "feel": "navigate",
        "propose": _propose_create_jd,
        # no execute — navigate-and-prefill; the human submits via the JD endpoint
        "capability": Capability.MANAGE_JD_LIBRARY,
        "label": "create a JD",
        "match": lambda m: ("jd" in m or "job description" in m),
    },
    "record_actual": {
        "feel": "confirm",
        "propose": _propose_record_actual,
        "execute": _execute_record_actual,
        "capability": Capability.UPDATE_OWN_ACTUALS,
        "label": "record a KPI actual",
        "match": lambda m: "record" in m
        and ("actual" in m or "kpi" in m or "progress" in m or any(c.isdigit() for c in m)),
    },
    "give_recognition": {
        "feel": "confirm",
        "propose": _propose_give_recognition,
        "execute": _execute_give_recognition,
        "capability": Capability.GIVE_RECOGNITION,
        "label": "give recognition",
        "match": lambda m: ("recogni" in m or "kudos" in m) and "approve" not in m,
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
