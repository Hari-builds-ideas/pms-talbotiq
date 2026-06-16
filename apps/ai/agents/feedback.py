"""
Agent 3 — Feedback Summarization (Large). Fills the Module-4
``FeedbackSummarizerProvider`` seam. Node sequence:

    consume the ANONYMISED payload (never raw givers) → LLM 4-section theme summary
    (gateway) → POST-LLM anonymity-breach check → return.

The POST-LLM breach check is LOAD-BEARING: the Module-4 PRE-LLM guard is email-only
and runs on the source bodies, so a name/email leak in the GENERATED text is caught
here and flagged ``anonymity_breach`` → the Module-4 task holds the summary
HRBP_HOLD (never auto-released). The summary always stays human-gated (HITL).
"""
from __future__ import annotations

import json

from apps.ai.evidence import confidence_with_sufficiency
from apps.ai.gateway import gateway
from apps.ai.graph import run_graph
from apps.ai.pii import contains_pii
from apps.ai.providers import llm_configured, register_fake_output
from apps.ai.schemas import NonEmpty
from apps.feedback.agent3 import FeedbackSummarizerNotConfiguredError
from apps.feedback.agent3 import FeedbackSummarizerProvider as _BaseFeedbackSummarizerProvider

AGENT_CODE = "agent3"
_SECTIONS = ("strengths", "growth", "themes", "risks")
#: Tightened: all 4 sections present + non-blank (a hollow section fails).
SCHEMA = {"sections": {s: NonEmpty(12) for s in _SECTIONS}}


def _payload_sufficiency(payload) -> float:
    """How much grounding the anonymised payload carries: more reviewers across
    more groups → higher confidence; one or two comments in a single group →
    lower (a thin summary, flag it)."""
    if not isinstance(payload, dict):
        return 0.6
    groups = payload.get("groups", {}) or {}
    total = sum(len(items) for items in groups.values())
    present = len([g for g, items in groups.items() if items])
    if total >= 5 and present >= 2:
        return 1.0
    if total >= 3:
        return 0.8
    if total >= 1:
        return 0.55
    return 0.3


def _node_llm(state):
    payload = state["payload"]
    volumes = payload.get("volumes") if isinstance(payload, dict) else None
    groups = payload.get("groups") if isinstance(payload, dict) else None
    prompt = (
        "Summarise this ANONYMISED 360 feedback into four evidence-based sections "
        "(strengths, growth, themes, risks). Reviewer groups are pseudonymised; "
        "cite how WIDELY a theme recurs (e.g. 'several peers') using the volumes — "
        "never an identity.\n"
        f"Per-group response volumes: {json.dumps(volumes)}.\n"
        f"Pseudonymised reviewer comments by group: {json.dumps(groups)}."
    )
    # subject_id identifies whose 360 it is (recipients know that); everything else
    # in the payload is already pseudonymised by Module 4.
    result = gateway.run(
        tenant=state["tenant_id"], agent_code=AGENT_CODE, prompt=prompt,
        model="feedback", schema=SCHEMA,
    )
    state["result"] = result
    if result.ok:
        state["confidence"] = confidence_with_sufficiency(
            result.confidence, _payload_sufficiency(payload)
        )
    else:
        state["_halt"] = result.status
    return state


def _node_breach_check(state):
    """POST-LLM anonymity-breach check: scan the GENERATED sections for any
    email-like identifier the pre-LLM email guard could not have caught (it ran on
    the source bodies). A hit flags a breach → the task holds for an HRBP."""
    sections = state["result"].content.get("sections", {})
    leaked = any(contains_pii(v) for v in sections.values())
    state["anonymity_breach"] = bool(leaked)
    return state


_NODES = [_node_llm, _node_breach_check]


class FeedbackSummarizerProvider(_BaseFeedbackSummarizerProvider):
    """LangGraph-backed Agent 3, gateway-fronted. ``configured`` follows the LLM
    gateway so production stays 503 until a provider is wired."""

    @property
    def configured(self) -> bool:  # type: ignore[override]
        return llm_configured()

    def summarize(self, payload) -> dict:
        # The Module-4 task runs summarize inside tenant_context; the gateway needs
        # the tenant for budget + usage, so resolve it from the bound context.
        from apps.tenancy.context import get_current_tenant_id

        tenant_id = get_current_tenant_id() or (
            payload.get("tenant_id") if isinstance(payload, dict) else None
        )
        state = run_graph(_NODES, {"payload": payload, "tenant_id": tenant_id})
        result = state.get("result")
        if state.get("_halt") == "NOT_CONFIGURED" or result is None:
            raise FeedbackSummarizerNotConfiguredError("Agent 3 (Feedback) is not configured.")
        if not result.ok:
            raise RuntimeError(f"Agent 3 unavailable: {result.status}")
        return {
            "sections": result.content["sections"],
            "confidence_score": state.get("confidence", result.confidence),
            "anonymity_breach": state.get("anonymity_breach", False),
        }


def _fake(prompt, model):
    return {
        "sections": {
            "strengths": "Consistently strong delivery noted by multiple reviewers.",
            "growth": "Could communicate trade-offs earlier.",
            "themes": "Reliable, collaborative, pragmatic.",
            "risks": "Some bottlenecking on reviews.",
        }
    }


register_fake_output(AGENT_CODE, _fake)
