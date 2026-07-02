"""
The agent PLANNER (OVERNIGHT_A2) — decompose a multi-step request into an ordered,
INERT plan the human approves step by step.

THE INVARIANT (unchanged from single-action propose-and-confirm): **the LLM only
plans** — it emits an ordered list of ACTION NAMES (+ a subject hint). It never
produces parameters, permissions, or SQL. Every step is then REALIZED in Python by
the SAME battle-tested ``_propose_*`` function the single-action path uses, so:

  * params are resolved DETERMINISTICALLY against only what the caller can see;
  * a step for an action the caller lacks capability for is dropped (checked here
    AND again at execute — defense in depth);
  * an out-of-scope / ambiguous / non-existent subject yields no confirm step (it
    becomes a ``clarify`` or is omitted with a GENERIC note — never revealing an
    out-of-scope person exists);
  * nothing executes on plan-emit — a plan is inert data until a per-step Approve.

Grounded reasons: each step's ``reason`` is composed in Python from the REAL facts
the propose function already verified (the resolved person/role/KPI, the review
state, scope). A step that can't be grounded (propose returned nothing) is dropped,
so every emitted step carries a grounded reason by construction.
"""
from __future__ import annotations

import re

from django.db import transaction

from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.ai.actions import ACTIONS, execute_action
from apps.ai.gateway import gateway
from apps.ai.models import ChatPlan, ChatPlanStep
from apps.ai.providers import register_fake_output
from apps.ai.sessions import resolve_person_reference
from apps.rbac.matrix import role_has_capability

AGENT_CODE = "planner"
#: The planner shares the fast/cheap chat tier (gpt-4o-mini) — no settings change.
MODEL = "chat"
PLAN_SCHEMA = {"steps": list, "summary": str}

#: Hard cap on realized steps (spec A2). Raw LLM steps beyond this are ignored.
MAX_STEPS = 5

#: Per-action template to synthesize a single-action message the existing propose
#: functions parse (keyword match + deterministic subject/param resolution). The
#: subject hint is inserted as DATA; propose still resolves scope itself.
_SYNTH = {
    "initiate_360": "start a 360 for {s}",
    "draft_review": "draft a review for {s}",
    "schedule_review": "schedule a review for {s}",
    "career_enrich": "enrich the development roadmap for {s}",
    "succession_enrich": "enrich the succession plan for {s}",
    "give_recognition": "give recognition to {s}",
    "create_jd": "create a jd for {s}",
    "approve_goals": "approve goals",
    "approve_goal": "approve the goal for {s}",
    "approve_reviews": "approve reviews",
    "record_actual": "{s}",  # subject carries the KPI + value phrase verbatim
    "update_kpi_actual": "{s}",  # subject carries the KPI + value phrase verbatim
    "respond_to_checkin": "respond to the check-in for {s}",
    "open_checkin": "start my check-in {s}",  # subject may carry the mood
}

_PERSON_DEIXIS = re.compile(r"\b(they|them|their|her|him|his|she|he|that person|same person|this person)\b", re.I)


def _synth_message(action: str, subject: str, original: str) -> str:
    tmpl = _SYNTH.get(action)
    subj = (subject or "").strip()
    if tmpl is None:
        return original
    if "{s}" not in tmpl:
        return tmpl
    return tmpl.format(s=subj) if subj else original


def _subject_label(proposal: dict) -> str:
    """Pull a human label out of a proposal's preview (employee / recipient / role / kpi)."""
    for row in proposal.get("preview") or []:
        for key in ("employee", "recipient", "role", "kpi"):
            if row.get(key):
                return str(row[key])
    return ""


def _reason_for(action: str, proposal: dict) -> str:
    """A grounded 'why' composed from the REAL facts the propose function verified.
    (The propose already confirmed scope/eligibility against live rows, so these
    statements are grounded, not hand-waved.)"""
    who = _subject_label(proposal)
    if proposal.get("feel") == "clarify":
        return proposal.get("summary", "I need one detail to proceed.")
    if action == "initiate_360":
        return f"{who} is in your team, so you can open a 360 feedback cycle for them."
    if action == "draft_review":
        return f"{who}'s review is in DRAFT and within your scope, so an AI draft is allowed."
    if action == "career_enrich":
        return f"{who} has an active development roadmap you manage; AI can enrich it as a draft."
    if action == "succession_enrich":
        return f"There's an active succession plan for {who}; your role can enrich it."
    if action == "record_actual":
        row = (proposal.get("preview") or [{}])[0]
        return f"“{row.get('kpi', '')}” is your own active KPI; recording {row.get('value', '')} updates your progress."
    if action == "give_recognition":
        return f"{who} is a colleague in your workspace; you can post recognition to them."
    if action == "approve_goal":
        return f"{who}'s goal is pending your approval and within your team, so you can approve it."
    if action == "approve_goals":
        return f"{len(proposal.get('params', {}).get('goal_ids', []))} goal(s) in your team are pending your approval."
    if action == "approve_reviews":
        return f"{len(proposal.get('params', {}).get('review_ids', []))} review(s) are pending your sign-off."
    if action == "schedule_review":
        return f"Opens Reviews with {who or 'the employee'} + the current cycle prefilled to schedule a review."
    if action == "respond_to_checkin":
        return f"{who} is your report; you can post a response to their weekly check-in."
    if action == "open_checkin":
        return "Starts your own weekly check-in — only you can write it."
    if action == "update_kpi_actual":
        row = (proposal.get("preview") or [{}])[0]
        return f"“{row.get('kpi', '')}” is your own active KPI; recording {row.get('value', '')} updates your progress."
    if action == "create_jd":
        return "Opens the JD Library where you fill in the details and generate the JD."
    return proposal.get("summary", "")


def _realize_step(user, session, action: str, subject: str, original: str, last_person: str):
    """Turn one planned (action, subject) into a realized proposal via the existing
    propose function — or ``None`` if the action is unknown / the caller lacks the
    capability / nothing actionable resolved. Returns ``(proposal_or_None, person_label)``."""
    spec = ACTIONS.get(action)
    if spec is None:
        return None, last_person  # unknown action — dropped
    cap = spec.get("capability")
    if cap is not None and not role_has_capability(user.role, cap):
        return None, last_person  # capability gate (also re-checked at execute)

    subj = (subject or "").strip()
    # A pronoun / empty subject → the person from earlier in THIS plan (or a prior
    # in-scope turn). Access is re-checked when the reference resolves.
    if (not subj or _PERSON_DEIXIS.search(subj)):
        person = resolve_person_reference(user, session, subj or original)
        subj = (getattr(person, "display_name", "") or "").strip() or last_person or subj

    proposal = spec["propose"](user, _synth_message(action, subj, original))
    if proposal is None:
        return None, last_person
    return proposal, (_subject_label(proposal) or last_person)


@transaction.atomic
def _persist_plan(user, session, message: str, summary: str, confidence, realized: list) -> ChatPlan:
    plan = ChatPlan.objects.create(
        tenant_id=user.tenant_id, owner=user, session=session,
        message=message[:8000], summary=summary[:2000], confidence=confidence,
    )
    for i, (action, proposal) in enumerate(realized):
        ChatPlanStep.objects.create(
            tenant_id=user.tenant_id,
            plan=plan,
            ordinal=i,
            action=action if proposal.get("feel") != "clarify" else "clarify",
            feel=proposal.get("feel", "confirm"),
            params=proposal.get("params", {}),
            summary=proposal.get("summary", "")[:2000],
            reason=_reason_for(action, proposal)[:2000],
            preview=proposal.get("preview", []),
            deeplink=proposal.get("deeplink", "") or "",
            prefill=proposal.get("prefill", {}) or {},
            candidates=proposal.get("candidates", []) or [],
        )
    return plan


def build_plan(user, session, message: str) -> dict:
    """Plan ``message`` for ``user`` in ``session``. Returns a status dict the view
    maps to HTTP: ``planned`` (a ChatPlan) | ``not_configured`` | ``budget`` | ``error``."""
    result = gateway.run(
        tenant=user.tenant_id, agent_code=AGENT_CODE, prompt=message, model=MODEL, schema=PLAN_SCHEMA
    )
    if result.status == "NOT_CONFIGURED":
        return {"status": "not_configured"}
    if result.status == "BUDGET_EXCEEDED":
        return {"status": "budget", "errors": result.errors}
    if not result.ok:
        return {"status": "error", "detail": result.status}

    raw_steps = result.content.get("steps") or []
    summary = (result.content.get("summary") or "").strip()

    realized: list = []
    omitted = 0
    last_person = ""
    for raw in raw_steps:
        if len(realized) >= MAX_STEPS:
            break
        if not isinstance(raw, dict):
            continue
        action = (raw.get("action") or "").strip()
        subject = (raw.get("subject") or "").strip()
        proposal, last_person = _realize_step(user, session, action, subject, message, last_person)
        if proposal is None:
            omitted += 1
            continue
        realized.append((action, proposal))

    if omitted and not summary:
        summary = "Here's what I can set up. Some requested steps couldn't be prepared with the information available."
    elif omitted:
        summary += " (Some requested steps couldn't be prepared with the information available.)"
    if not realized and not summary:
        summary = ("I couldn't turn that into a step I'm able to prepare. "
                   "Tell me who or what it's for, or ask me what I can do.")

    plan = _persist_plan(user, session, message, summary, result.confidence, realized)
    return {"status": "planned", "plan": plan}


#: Which resolved param id maps to which ref type — so a later turn can say "her" /
#: "the review we just drafted" and resolve it (access always re-checked at use).
_PARAM_REF_TYPE = {
    "subject_id": "user",
    "recipient_user_id": "user",
    "review_id": "review",
    "roadmap_id": "roadmap",
    "plan_id": "succession_plan",
    "cycle_id": "feedback_cycle",
}


def refs_for_plan(plan: ChatPlan) -> list[dict]:
    """The in-scope objects a plan grounded in — recorded on the assistant turn so a
    later turn can reference them. Data only; access is re-checked on use."""
    refs: list[dict] = []
    for step in plan.steps.all():
        label = _subject_label({"preview": step.preview})
        for key, rtype in _PARAM_REF_TYPE.items():
            rid = (step.params or {}).get(key)
            if rid:
                refs.append({"type": rtype, "id": str(rid), "label": label})
    return refs


# ── per-step approval (OVERNIGHT_A3) — execute exactly ONE step, on Approve ──────


def get_plan_for_owner(user, plan_id) -> ChatPlan:
    """Fetch a plan for the caller: their OWN plan (403 if it's someone else's in the
    same tenant, 404 if it doesn't exist / is cross-tenant — the scoped manager hides
    a cross-tenant id, so this never leaks another tenant)."""
    plan = ChatPlan.objects.filter(id=plan_id).prefetch_related("steps").first() if _looks_uuid(plan_id) else None
    if plan is None:
        raise NotFound("No such plan.")
    if plan.owner_id != user.id:
        raise PermissionDenied("That plan isn't yours.")
    return plan


def _looks_uuid(value) -> bool:
    import uuid as _uuid

    try:
        _uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def approve_step(user, plan_id, step_id) -> dict:
    """Approve and run EXACTLY ONE step. Concurrency-safe: the plan row is locked
    while the step transitions PENDING→APPROVED, so two racing approvals execute the
    step at most once. Idempotent (an already-done step re-returns its result).
    Approving out of order is allowed but flagged (``out_of_order``); earlier steps
    are NEVER auto-run. The execute path re-checks capability + scope (a forbidden /
    out-of-scope step raises → the view maps 403/404), exactly like the human path."""
    from django.db import transaction

    from apps.ai.models import ChatPlanStep as Step

    # Ownership + existence first (403 vs 404, no cross-tenant leak).
    get_plan_for_owner(user, plan_id)

    claimed = False
    with transaction.atomic():
        plan = ChatPlan.objects.select_for_update().filter(id=plan_id, owner=user).first()
        if plan is None:
            raise NotFound("No such plan.")
        step = plan.steps.filter(id=step_id).first() if _looks_uuid(step_id) else None
        if step is None:
            raise NotFound("No such step in this plan.")

        out_of_order = plan.steps.filter(ordinal__lt=step.ordinal, status=Step.Status.PENDING).exists()
        base = {
            "plan_id": str(plan.id), "step_id": str(step.id), "action": step.action,
            "feel": step.feel, "ordinal": step.ordinal, "out_of_order": out_of_order,
        }

        if step.status == Step.Status.DONE:
            return {**base, "status": "done", "idempotent": True, "result": step.result}
        if step.status == Step.Status.APPROVED:
            # Another approval already claimed it — don't double-execute.
            return {**base, "status": "in_progress", "idempotent": True, "result": step.result}
        if step.status == Step.Status.SKIPPED:
            return {**base, "status": "skipped", "idempotent": True}

        if step.feel == Step.Feel.CLARIFY:
            # Can't "approve" a question — surface it (+ candidates); leave it pending.
            return {**base, "status": "needs_clarification",
                    "question": step.summary, "candidates": step.candidates}
        if step.feel == Step.Feel.NAVIGATE:
            step.status = Step.Status.DONE
            step.result = {"deeplink": step.deeplink, "prefill": step.prefill}
            step.save(update_fields=["status", "result"])
            return {**base, "status": "done", "idempotent": False,
                    "deeplink": step.deeplink, "prefill": step.prefill}

        # CONFIRM (PENDING or a prior FAILED retry): claim it under the lock.
        step.status = Step.Status.APPROVED
        step.save(update_fields=["status"])
        claimed = True
        action, params, ordinal = step.action, step.params, step.ordinal

    # Lock released. Execute the SAME audited service the human path uses; on any
    # capability/scope error mark FAILED and propagate (DRF → 403/404/400).
    try:
        result = execute_action(user, action, params)
    except (PermissionDenied, NotFound, ValidationError):
        Step.objects.filter(id=step_id).update(status=Step.Status.FAILED)
        raise
    except Exception as exc:  # noqa: BLE001 — never leave a step wedged in APPROVED
        Step.objects.filter(id=step_id).update(status=Step.Status.FAILED, result={"error": type(exc).__name__})
        raise
    Step.objects.filter(id=step_id).update(status=Step.Status.DONE, result=result)
    return {
        "plan_id": str(plan_id), "step_id": str(step_id), "action": action,
        "feel": "confirm", "ordinal": ordinal, "out_of_order": out_of_order,
        "status": "done", "idempotent": False, "result": result,
    }


# ── deterministic fake planner (tests + no-key path) ────────────────────────────
#
# Decompose the message into clauses (on 'and' / 'then' / ',' / ';') and, per clause,
# emit the FIRST registered action whose match() fires, with the subject after
# "for"/"to" (or a pronoun for cross-step reference). Mirrors how a real LLM would
# split a multi-step outcome into ordered steps — deterministically, no network.

_CLAUSE_SPLIT = re.compile(r"\band\b|\bthen\b|\balso\b|[,;]", re.I)
_SUBJECT_AFTER = re.compile(r"\b(?:for|to)\s+([A-Za-z][\w'\-]*(?:\s+[A-Z][\w'\-]*)?)", re.I)


def _extract_subject(clause: str) -> str:
    m = _SUBJECT_AFTER.search(clause or "")
    if m:
        return m.group(1).strip()
    p = _PERSON_DEIXIS.search(clause or "")
    return p.group(0) if p else ""


def _fake_planner(prompt, model):
    text = prompt or ""
    clauses = [c.strip() for c in _CLAUSE_SPLIT.split(text) if c and c.strip()]
    if not clauses:
        clauses = [text]
    steps = []
    for clause in clauses:
        low = clause.lower()
        for name, spec in ACTIONS.items():
            try:
                if spec["match"](low):
                    steps.append({"action": name, "subject": _extract_subject(clause)})
                    break
            except Exception:  # noqa: BLE001 — a bad match lambda must not crash the fake
                continue
    return {"steps": steps[:MAX_STEPS], "summary": "Planned the requested steps for your approval."}


register_fake_output(AGENT_CODE, _fake_planner)
