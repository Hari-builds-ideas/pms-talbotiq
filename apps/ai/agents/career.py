"""
Career Roadmap (Large). Fills the Module-9 ``CareerRoadmapProvider`` seam: the
DETERMINISTIC gap (M9) + baseline tiers → a gateway LLM ENRICHED advisory tiered
path. NEVER auto-promotion (the Module-9 ``advisory`` DB CHECK still holds); the
Module-9 task locks the result as a NEW source=AI roadmap DRAFT for human
acceptance. ``configured`` follows the gateway (prod 503). Surface is
entitlement-gated with ``career_roadmap`` (FULL_AI) at go-live.
"""
from __future__ import annotations

from apps.ai.gateway import gateway
from apps.ai.providers import llm_configured, register_fake_output
from apps.career.roadmap_agent import CareerRoadmapNotConfiguredError
from apps.career.roadmap_agent import CareerRoadmapProvider as _BaseCareerRoadmapProvider

AGENT_CODE = "career_roadmap"
SCHEMA = {"tiers": list}


class CareerRoadmapProvider(_BaseCareerRoadmapProvider):
    @property
    def configured(self) -> bool:  # type: ignore[override]
        return llm_configured()

    def draft(self, *, employee_id, target_label, gap, baseline_tiers) -> dict:
        from apps.tenancy.context import get_current_tenant_id

        prompt = (
            f"Draft an advisory development roadmap toward {target_label}. The "
            f"deterministic gap is {gap}; the baseline tiers are {baseline_tiers}. "
            "Advisory only — never a promotion instruction."
        )
        result = gateway.run(
            tenant=get_current_tenant_id(), agent_code=AGENT_CODE, prompt=prompt,
            model="career", schema=SCHEMA,
        )
        if result.status == "NOT_CONFIGURED":
            raise CareerRoadmapNotConfiguredError("Career Roadmap agent is not configured.")
        if not result.ok:
            raise RuntimeError(f"Career Roadmap unavailable: {result.status}")
        return {"tiers": result.content["tiers"], "confidence_score": result.confidence}


def _fake(prompt, model):
    return {
        "tiers": [
            {"index": 0, "title": "Reach HIGH sustained performance", "detail": "Focus areas …", "basis": "AI"},
            {"index": 1, "title": "Lead a cross-team initiative", "detail": "Stretch …", "basis": "AI"},
        ]
    }


register_fake_output(AGENT_CODE, _fake)
