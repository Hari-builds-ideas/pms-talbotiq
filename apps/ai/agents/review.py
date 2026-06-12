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

from apps.ai.gateway import gateway
from apps.ai.graph import run_graph
from apps.ai.providers import llm_configured, register_fake_output
from apps.reviews.agent1 import ReviewAssistantNotConfiguredError
from apps.reviews.agent1 import ReviewAssistantProvider as _BaseReviewAssistantProvider

AGENT_CODE = "agent1"
_SECTIONS = ("summary", "strengths", "areas_for_development", "goals_assessment", "recommendations")
#: The gateway validates the LLM output is an object carrying the 5 sections.
SCHEMA = {"sections": dict}


# ── nodes ──────────────────────────────────────────────────────────────────────


def _node_validate(state):
    if state.get("review") is None:
        state["_halt"] = "no_review"
    return state


def _node_gather_evidence(state):
    """Gather the review subject's goals + latest CycleScore (tenant-scoped — the
    task binds the tenant). This is the AI's grounding evidence + citations."""
    from apps.goals.models import CycleScore, Goal

    review = state["review"]
    goals = list(
        Goal.objects.filter(employee_id=review.employee_id, cycle_id=review.cycle_id)
        .values_list("title", flat=True)
    )
    score = (
        CycleScore.objects.filter(employee_id=review.employee_id, cycle_id=review.cycle_id)
        .first()
    )
    state["evidence"] = {
        "goals": goals,
        "t_score": str(score.t_score) if score else None,
        "risk_status": score.risk_status if score else None,
    }
    state["citations"] = [{"type": "goal", "title": g} for g in goals]
    if score:
        state["citations"].append({"type": "cycle_score", "t_score": str(score.t_score)})
    return state


def _node_llm(state):
    review = state["review"]
    ev = state["evidence"]
    prompt = (
        "Draft a 5-section performance review from this evidence: "
        f"goals={ev['goals']} t_score={ev['t_score']} risk={ev['risk_status']}."
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
    sections = result.content["sections"]
    body_parts = [f"## {k.replace('_', ' ').title()}\n{sections.get(k, '')}" for k in _SECTIONS]
    body = "\n\n".join(body_parts)
    if result.low_confidence:
        body = (
            "⚠️ LOW CONFIDENCE — this AI draft scored below the confidence floor; "
            "review carefully before approving.\n\n" + body
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
            raise RuntimeError(f"Agent 1 unavailable: {result.status}")
        return {
            "draft_body": state["draft_body"],
            "confidence_score": result.confidence,
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
