"""
The conversation STATE MACHINE (AGENT_REBUILD/B) — deterministic turn routing that
runs BEFORE any LLM classification.

Why this module exists
----------------------
The assistant used to hand every message to the LLM classifier first, and only
messages the model labelled ``write`` ever reached the planner. That single ordering
mistake caused the worst live bugs:

  * A pending follow-up ("how are you feeling this week, 1–5?") could never be
    answered. A bare "5" classifies as *general*, so it fell through to the read path
    and the SAME question came back — forever. The slot-filling code existed; it was
    simply unreachable.
  * Plainly imperative commands the model didn't happen to label ``write``
    ("start my check-in", "log my mood", "shout out to Ada") never reached the
    planner at all, and got the capability blurb instead.

So: whether the user is ANSWERING A QUESTION, CANCELLING, REPEATING THE LAST ACTION,
or ISSUING A COMMAND is decided in Python, from session state and the action registry
— facts we already hold. The LLM keeps the job it is actually good at (understanding
open-ended questions) and loses the job it kept getting wrong (routing).

The order of the machine, per turn
----------------------------------
1. **Cancel** ("never mind", "stop", "cancel") → clear any pending slot, acknowledge.
2. **New command** — the message matches a registered action → ABANDON the pending
   slot and route to the planner. The user is never trapped and never ignored.
3. **Answer the pending slot** — parse with the slot's OWN parser (a ``mood`` slot
   accepts "5"; a ``person`` slot does not) → resume THAT action, filled.
4. **Topic change while pending** (a question) → abandon the slot, fall through to
   the normal read path so the question gets answered.
5. **Invalid answer** → say specifically why and re-ask ONCE with the expected
   format. A second miss abandons the slot rather than looping.
6. **"Do the same for <person>"** → repeat the LAST action type with the newly
   resolved person (company-wide directory, same as the action it repeats).
7. **Imperative command** → straight to the planner, no LLM classification needed.

Everything it produces is still an INERT plan behind the human-approval gate, and
every person lookup still goes through the one company-wide directory resolver while
data access stays permission-scoped and re-checked. This module changes WHEN we
decide, never WHAT the user is allowed to do.
"""
from __future__ import annotations

import re

from apps.ai.models import ChatPlan, ChatPlanStep

#: Explicit abandonment. Deliberately narrow — these must be the user's whole message
#: (or nearly), so "stop the review cycle" is a command, not a cancel.
_CANCEL_RE = re.compile(
    r"^\s*(?:no[,.\s]*)?(?:never\s*mind|nevermind|forget\s+it|forget\s+that|cancel(?:\s+that|\s+it)?|"
    r"stop(?:\s+that|\s+it)?|drop\s+it|abort|quit|leave\s+it)\s*[.!]?\s*$",
    re.I,
)

#: "do the same for X" / "same for X" / "do that for X too" — repeat the last action
#: on a new person. The trailing group is the person phrase, resolved company-wide.
_DO_THE_SAME_RE = re.compile(
    r"^\s*(?:and\s+|now\s+|also\s+)?(?:can\s+you\s+|please\s+)?"
    r"(?:do|make|give|run|send)?\s*(?:the\s+)?same\s+(?:thing\s+|one\s+|again\s+)?"
    r"(?:for|to|with)\s+(.+?)\s*(?:too|as\s+well|please)?\s*[.!?]?\s*$",
    re.I,
)

#: A question, not an instruction — used to tell a topic change from a slot answer.
_QUESTION_RE = re.compile(
    r"^\s*(?:how|what|who|whose|which|when|why|where|is|are|was|were|does|do|did|"
    r"can|could|should|would|will|am|any|tell\s+me|show\s+me|list)\b",
    re.I,
)

#: How many times we re-ask one slot before abandoning it. One. The loop WAS the bug.
_MAX_REASKS = 1


# ── slot parsers — each returns the SUBJECT PHRASE to resume the action with, or
#    None when the message isn't a valid answer to that particular question ────────


def _parse_mood(message: str):
    """A mood 1–5 the user stated, however they said it: "5", "mood 4", "4/5",
    "feeling good", "I'm ok". Returns the canonical "mood N" phrase the check-in
    proposer parses, or None."""
    from apps.ai.actions import _extract_mood

    text = (message or "").strip()
    bare = re.fullmatch(r"[^\d]{0,20}?([1-5])(?:\s*/\s*5)?[^\d]{0,20}?", text)
    if bare:
        return f"mood {bare.group(1)}"
    mood = _extract_mood(text)
    return f"mood {mood}" if mood is not None else None


def _parse_person(message: str):
    """A NAME answering "who?". Rejects questions and anything with no name-shaped
    content, so a topic change is never swallowed as an answer. The directory
    resolver decides whether the name actually matches anyone."""
    from apps.ai.directory import _name_tokens

    text = (message or "").strip()
    if not text or "?" in text or _QUESTION_RE.match(text):
        return None
    return text if _name_tokens(text) else None


def _parse_kpi_value(message: str):
    """A KPI + value ("85 for Uptime", "record 85 for Uptime"). Needs a number —
    without one there is nothing to record."""
    text = (message or "").strip()
    if not text or not any(c.isdigit() for c in text):
        return None
    return text


def _parse_role(message: str):
    """A critical-role name. Same shape as a person answer, different lookup."""
    return _parse_person(message)


#: slot name → (parser, what to say when the answer doesn't parse). The re-ask text
#: states the EXPECTED FORMAT, because "I didn't get that" is what made it loop.
_SLOTS = {
    "mood": (_parse_mood, "I need a number from 1 to 5 for how this week felt — e.g. “4”."),
    # No seed person appears in user-facing text: on another tenant a made-up example
    # name is just confusing. Ask for the shape of the answer, not a specific person.
    "person": (_parse_person, "I need a person's full name, or their email address."),
    "kpi_value": (_parse_kpi_value, "I need a KPI and a number — e.g. “85 for Uptime”."),
    "role": (_parse_role, "I need the name of a critical role — e.g. “Head of Platform”."),
}


def parse_slot_answer(slot, message: str):
    """The subject phrase ``message`` supplies for ``slot``, or ``None`` if it isn't a
    valid answer to that question. Public so the planner's direct entry point parses
    answers identically to the chat path."""
    parser, _ = _SLOTS.get(slot, (None, None))
    return parser(message) if parser is not None else None


# ── pending-slot state ───────────────────────────────────────────────────────────


def pending_slot(session):
    """The clarify step this session is waiting on an answer for, or ``None``.

    Only a step that declares a ``clarify_slot`` counts: a dead-end message ("there's
    no plan for that role yet") must never arm a slot, or it swallows the next turn.
    """
    if session is None:
        return None
    plan = (
        ChatPlan.objects.filter(session=session)
        .order_by("-created_at")
        .prefetch_related("steps")
        .first()
    )
    if plan is None:
        return None
    step = (
        plan.steps.filter(feel=ChatPlanStep.Feel.CLARIFY, status=ChatPlanStep.Status.PENDING)
        .order_by("ordinal")
        .first()
    )
    if step is None:
        return None
    params = step.params or {}
    if not params.get("clarify_slot") or params.get("clarify_action") not in _known_actions():
        return None
    return step


def _known_actions():
    from apps.ai.actions import ACTIONS

    return ACTIONS


def abandon_slot(step) -> None:
    """Close a pending question the user has moved on from. SKIPPED (not deleted) so
    the plan history stays an honest record of what was asked and dropped."""
    if step is not None:
        ChatPlanStep.objects.filter(id=step.id, status=ChatPlanStep.Status.PENDING).update(
            status=ChatPlanStep.Status.SKIPPED
        )


# ── intent detection (deterministic, from the action registry) ───────────────────


def matched_action(message: str):
    """The registered action this message NAMES, or ``None``. The registry's own
    ``match`` predicates, in registry order — the same first-match-wins rule the
    planner uses, so routing here and realization there can never disagree."""
    low = (message or "").lower()
    for name, spec in _known_actions().items():
        try:
            if spec["match"](low):
                return name
        except Exception:  # noqa: BLE001 — one bad predicate must not break routing
            continue
    return None


def is_open_reference(message: str) -> bool:
    """"Open the draft", "show me that review" — a DEFINITE reference to something
    already in the conversation. It's navigation to an existing record, not a command
    to start a new task, so the reference resolver owns it."""
    from apps.ai.agents.chat import _OPEN_REF_RE

    return bool(_OPEN_REF_RE.search(message or ""))


def is_command(message: str) -> bool:
    """True when the message is an IMPERATIVE that names a registered action —
    "start my check-in", "give recognition to Ada". Two things are deliberately NOT
    commands: a question that merely mentions an action ("how many goals should I
    approve?"), which is a READ, and a definite reference ("open the draft to review
    it"), which is navigation. So this only ever ADDS write routing — it never steals
    a question or a reference."""
    text = (message or "").strip()
    if not text or matched_action(text) is None:
        return False
    if is_open_reference(text):
        return False
    return not (text.endswith("?") or _QUESTION_RE.match(text))


# ── "do the same for X" ──────────────────────────────────────────────────────────


def last_action_in_session(session):
    """The action type of the most recent real task in this conversation, for
    "do the same for X".

    Preference order: an action the user actually APPROVED, then one that was
    proposed, then — last — the action a still-unanswered QUESTION was gathering a
    detail for. That last fallback matters: if the previous recognition stalled on
    "which Priya do you mean?", the user's intent was still *recognition*, and
    "do the same for someone else" must repeat THAT, not fall through to a data
    lookup on the new name (which is how it ended up answering "you don't have
    access to their data" — an answer to a question nobody asked).
    """
    if session is None:
        return None
    plans = (
        ChatPlan.objects.filter(session=session).order_by("-created_at").prefetch_related("steps")[:20]
    )
    known = _known_actions()
    proposed = pending = None
    for plan in plans:
        for step in sorted(plan.steps.all(), key=lambda s: -s.ordinal):
            if step.feel == ChatPlanStep.Feel.CLARIFY:
                asked = (step.params or {}).get("clarify_action")
                if pending is None and asked in known:
                    pending = asked
                continue
            if step.action not in known:
                continue
            if step.status == ChatPlanStep.Status.DONE:
                return step.action
            if proposed is None:
                proposed = step.action
    return proposed or pending


# ── the machine ──────────────────────────────────────────────────────────────────


def _planned(plan):
    return {"status": "plan", "intent": "write", "plan": plan}


def _spoken(answer):
    return {"status": "ok", "intent": "general", "data": [], "answer": answer}


def route_turn(caller, message: str, *, session):
    """Decide this turn deterministically, or return ``None`` to let the normal
    LLM-classified path handle it.

    Returns a ``chat_answer``-shaped dict. Any plan it produces is inert until the
    human approves a step, and every action re-resolves its subject and re-checks
    capability + scope inside the propose/execute functions — this only decides WHICH
    action the turn is about.
    """
    from apps.ai.planner import build_plan, fill_slot, repeat_action

    text = (message or "").strip()
    if not text or session is None:
        return None

    step = pending_slot(session)

    # 1 — explicit cancel always wins, pending or not.
    if _CANCEL_RE.match(text):
        if step is None:
            return None  # nothing to cancel — let the normal path answer.
        abandon_slot(step)
        return _spoken("Okay — I've cancelled that. What would you like to do instead?")

    if step is not None:
        params = step.params or {}
        slot = params.get("clarify_slot")
        parser, expected = _SLOTS.get(slot, (None, None))
        asked = int(params.get("clarify_reasks") or 0)

        # 2 — anything that is plainly a NEW request outranks the pending question:
        # obey it and drop the question. Being trapped was the bug.
        if is_command(text) or is_open_reference(text) or _DO_THE_SAME_RE.match(text):
            abandon_slot(step)
        elif parser is None:
            abandon_slot(step)  # an unknown slot kind can never be filled — let go.
        else:
            answer = parser(text)
            plan = (
                fill_slot(caller, session, step, answer, text, reasks=asked + 1)
                if answer is not None else None
            )
            abandon_slot(step)  # this question is settled either way — never re-armed
            if plan is not None:
                # 3 — the answer resolved (or produced a MORE specific question).
                return _planned(plan)
            if _QUESTION_RE.match(text) or text.endswith("?"):
                pass  # 4 — a question mid-question is a topic change, not a bad answer.
            elif asked < _MAX_REASKS:
                # 5 — invalid: say exactly what's expected and re-ask ONCE.
                return _planned(_reask(caller, session, step, expected, asked + 1))
            else:
                return _spoken(
                    f"I still didn't catch that, so I've dropped the question. {expected} "
                    "Or tell me something else you'd like to do."
                )

    # 6 — "do the same for <someone else>": repeat the last action, new person.
    same = _DO_THE_SAME_RE.match(text)
    if same:
        action = last_action_in_session(session)
        if action:
            plan = repeat_action(caller, session, action, same.group(1).strip(), text)
            if plan is not None:
                return _planned(plan)

    # 7 — a plainly imperative command goes straight to the planner.
    if is_command(text):
        out = build_plan(caller, session, text)
        if out.get("status") == "planned":
            return _planned(out["plan"])
        return None  # not_configured / budget / error → the normal path reports it

    return None


def _reask(caller, session, step, expected: str, attempt: int):
    """Re-ask the SAME question once, carrying the slot forward with its attempt
    count, and leading with the expected format so the user can actually comply."""
    from apps.ai.planner import persist_clarify

    params = step.params or {}
    question = f"{expected} ({step.summary.strip()})" if step.summary else expected
    return persist_clarify(
        caller, session, question,
        slot=params.get("clarify_slot"),
        action=params.get("clarify_action"),
        original=params.get("clarify_original", ""),
        reasks=attempt,
        candidates=step.candidates or [],
    )
