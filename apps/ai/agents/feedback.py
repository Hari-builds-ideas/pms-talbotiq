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

from apps.ai.gateway import gateway
from apps.ai.graph import run_graph
from apps.ai.pii import contains_pii
from apps.ai.providers import llm_configured, register_fake_output
from apps.feedback.agent3 import FeedbackSummarizerNotConfiguredError
from apps.feedback.agent3 import FeedbackSummarizerProvider as _BaseFeedbackSummarizerProvider

AGENT_CODE = "agent3"
_SECTIONS = ("strengths", "growth", "themes", "risks")
SCHEMA = {"sections": dict}


def _node_llm(state):
    payload = state["payload"]
    prompt = (
        "Summarise this ANONYMISED 360 feedback into 4 sections "
        f"(strengths, growth, themes, risks). Payload: {payload}"
    )
    # subject_id identifies whose 360 it is (recipients know that); everything else
    # in the payload is already pseudonymised by Module 4.
    result = gateway.run(
        tenant=state["tenant_id"], agent_code=AGENT_CODE, prompt=prompt,
        model="feedback", schema=SCHEMA,
    )
    state["result"] = result
    if not result.ok:
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
            "confidence_score": result.confidence,
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
