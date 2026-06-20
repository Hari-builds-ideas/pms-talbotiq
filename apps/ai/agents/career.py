"""
Career Roadmap (Large). Fills the Module-9 ``CareerRoadmapProvider`` seam: the
DETERMINISTIC gap (M9) + baseline tiers → a gateway LLM ENRICHED advisory tiered
path. NEVER auto-promotion (the Module-9 ``advisory`` DB CHECK still holds); the
Module-9 task locks the result as a NEW source=AI roadmap DRAFT for human
acceptance. ``configured`` follows the gateway (prod 503). Surface is
entitlement-gated with ``career_roadmap`` (FULL_AI) at go-live.
"""
from __future__ import annotations

import json

from apps.ai.evidence import confidence_with_sufficiency
from apps.ai.gateway import gateway
from apps.ai.exceptions import AgentUnavailable
from apps.ai.providers import llm_configured, register_fake_output
from apps.career.roadmap_agent import CareerRoadmapNotConfiguredError
from apps.career.roadmap_agent import CareerRoadmapProvider as _BaseCareerRoadmapProvider

AGENT_CODE = "career_roadmap"
SCHEMA = {"tiers": list}


def _gap_sufficiency(gap) -> float:
    """A real gap (a known current band + named weak categories) grounds specific
    tiers; a fully-unknown gap can only yield generic advice → lower confidence."""
    if not isinstance(gap, dict):
        return 0.6
    has_band = bool(gap.get("current_performance_band")) and gap.get(
        "current_performance_band"
    ) != "UNKNOWN"
    weak = gap.get("weak_categories") or []
    if has_band and weak:
        return 1.0
    if has_band or weak:
        return 0.75
    return 0.5


class CareerRoadmapProvider(_BaseCareerRoadmapProvider):
    @property
    def configured(self) -> bool:  # type: ignore[override]
        return llm_configured()

    def draft(self, *, employee_id, target_label, gap, baseline_tiers) -> dict:
        from apps.tenancy.context import get_current_tenant_id

        prompt = (
            f"Draft an ADVISORY development roadmap toward '{target_label}'.\n"
            f"Deterministic skill gap (current vs required performance band + the "
            f"employee's at-risk goal categories): {json.dumps(gap)}.\n"
            f"Baseline tiers to refine: {json.dumps(baseline_tiers)}.\n"
            "Produce 2-4 ordered tiers, each targeting a SPECIFIC named gap with a "
            "concrete focus, why it matters (basis), and what 'done' looks like. "
            "Advisory only — never a promotion instruction."
        )
        result = gateway.run(
            tenant=get_current_tenant_id(), agent_code=AGENT_CODE, prompt=prompt,
            model="career", schema=SCHEMA,
        )
        if result.status == "NOT_CONFIGURED":
            raise CareerRoadmapNotConfiguredError("Career Roadmap agent is not configured.")
        if not result.ok:
            raise AgentUnavailable(result.status, f"Career Roadmap unavailable: {result.status}")
        return {
            "tiers": result.content["tiers"],
            "confidence_score": confidence_with_sufficiency(
                result.confidence, _gap_sufficiency(gap)
            ),
        }


def _fake(prompt, model):
    return {
        "tiers": [
            {"index": 0, "title": "Reach HIGH sustained performance", "detail": "Focus areas …", "basis": "AI"},
            {"index": 1, "title": "Lead a cross-team initiative", "detail": "Stretch …", "basis": "AI"},
        ]
    }


register_fake_output(AGENT_CODE, _fake)
