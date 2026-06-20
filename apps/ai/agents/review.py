"""
Agent 1 — Review Assistant (Large). Fills the Module-3 ``ReviewAssistantProvider``
seam. Node sequence (Doc 3 §5 safeguard pipeline), run via the in-repo graph
runner; the single LLM step goes through the ``LLMGateway`` (budget → PII-scrub →
schema-validate → meter → confidence):

    validate input → gather evidence (tenant-scoped goals/scores) → check evidence
    sufficiency → LLM drafts 5 sections (gateway) → structure to the contract →
    confidence + citations → (if confidence < 0.70 attach a yellow warning, still a
    draft).

The Module-3 task then LOCKS the result PENDING_HUMAN_REVIEW and audits it — an AI
draft is NEVER published directly. ``configured`` delegates to the gateway, so in
production (no LLM_PROVIDER) this reports unconfigured and the seam 503s; tests set
``LLM_PROVIDER=FakeLLMProvider`` to run the whole graph with no network.
"""
from __future__ import annotations

import json

from apps.ai.evidence import confidence_with_sufficiency, review_evidence
from apps.ai.gateway import DEFAULT_CONFIDENCE_FLOOR, gateway
from apps.ai.exceptions import AgentUnavailable
from apps.ai.graph import run_graph
from apps.ai.providers import llm_configured, register_fake_output
from apps.ai.schemas import NonEmpty
from apps.reviews.agent1 import ReviewAssistantNotConfiguredError
from apps.reviews.agent1 import ReviewAssistantProvider as _BaseReviewAssistantProvider

AGENT_CODE = "agent1"
_SECTIONS = ("summary", "strengths", "areas_for_development", "goals_assessment", "recommendations")
#: Tightened: the output MUST carry all 5 sections, each a non-blank string (a
#: missing / empty section fails validation → SCHEMA_INVALID, no hollow draft).
SCHEMA = {"sections": {s: NonEmpty(12) for s in _SECTIONS}}


# ── nodes ──────────────────────────────────────────────────────────────────────


def _node_validate(state):
    if state.get("review") is None:
        state["_halt"] = "no_review"
    return state


def _node_gather_evidence(state):
    """Assemble the RICH grounding for the subject: name + goals (with KPI
    target/actual/attainment %) + computed cycle score. Tenant-scoped (the task
    binds the tenant). Drives both the prompt and the citations."""
    ev = review_evidence(state["review"])
    state["evidence"] = ev
    state["citations"] = ev["citations"]
    return state


def _node_llm(state):
    review = state["review"]
    ev = state["evidence"]
    prompt = (
        f"Subject first name: {ev['subject_name']}.\n"
        f"Computed cycle score: {json.dumps(ev['score'])}.\n"
        f"Goals with KPIs (target / latest actual / attainment %): "
        f"{json.dumps(ev['goals'])}.\n"
        "Write the five-section review grounded in these specific goals, KPIs and "
        "numbers. Name the person; cite the actual goals and figures."
    )
    result = gateway.run(
        tenant=review.tenant_id, agent_code=AGENT_CODE, prompt=prompt,
        model="review", schema=SCHEMA,
    )
    state["result"] = result
    if not result.ok:
        state["_halt"] = result.status
    return state


def _node_structure(state):
    result = state["result"]
    ev = state["evidence"]
    sections = result.content["sections"]
    # Calibrate confidence to evidence sufficiency: a polished answer on thin
    # grounding still reads as lower confidence (and trips the floor warning).
    confidence = confidence_with_sufficiency(result.confidence, ev["evidence_sufficiency"])
    state["confidence"] = confidence
    body_parts = [f"## {k.replace('_', ' ').title()}\n{sections.get(k, '')}" for k in _SECTIONS]
    body = "\n\n".join(body_parts)
    if confidence < DEFAULT_CONFIDENCE_FLOOR:
        body = (
            "⚠️ LOW CONFIDENCE — this AI draft scored below the confidence floor "
            "(thin evidence or a low-confidence model response); review carefully "
            "before approving.\n\n" + body
        )
    state["draft_body"] = body
    return state


_NODES = [_node_validate, _node_gather_evidence, _node_llm, _node_structure]


# ── provider ────────────────────────────────────────────────────────────────────


class ReviewAssistantProvider(_BaseReviewAssistantProvider):
    """LangGraph-backed Agent 1, gateway-fronted. ``configured`` follows the LLM
    gateway so production stays 503 until a provider is wired."""

    @property
    def configured(self) -> bool:  # type: ignore[override]
        return llm_configured()

    def draft(self, review) -> dict:
        state = run_graph(_NODES, {"review": review})
        result = state.get("result")
        if state.get("_halt") == "NOT_CONFIGURED" or result is None:
            raise ReviewAssistantNotConfiguredError("Agent 1 (Review) is not configured.")
        if not result.ok:
            # Budget/schema/provider problem — do NOT fabricate; let the Module-3
            # task log it and leave the review in AI_DRAFTING.
            raise AgentUnavailable(result.status, f"Agent 1 unavailable: {result.status}")
        return {
            "draft_body": state["draft_body"],
            "confidence_score": state.get("confidence", result.confidence),
            "citations": state.get("citations"),
        }


# ── deterministic fake output (tests / demo) ──────────────────────────────────


def _fake(prompt, model):
    return {
        "sections": {
            "summary": "Solid, consistent contributor this cycle.",
            "strengths": "Delivery and collaboration.",
            "areas_for_development": "Stakeholder communication.",
            "goals_assessment": "Met the majority of committed goals.",
            "recommendations": "Stretch into a cross-team initiative next cycle.",
        }
    }


register_fake_output(AGENT_CODE, _fake)
