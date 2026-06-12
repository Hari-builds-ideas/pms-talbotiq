"""
Agent 4 — Successor Planning (Large). Fills the Module-8 ``SuccessionAnalyzerProvider``
seam. It ENRICHES the always-available DETERMINISTIC analysis (the M8 engine) with
an LLM narrative + confidence; the Module-8 task locks the result as a NEW
``source=AI`` SuccessionPlan PENDING_HUMAN_REVIEW and leaves the deterministic plan
COMPLETELY INTACT.

DATA BOUNDARY: the enrichment reads INTERNAL signals only — the deterministic
analysis (CycleScore-derived readiness/coverage). It NEVER pulls raw 360 givers
(anonymised themes could feed it later via the M4 anonymiser; raw givers never).
"""
from __future__ import annotations

from apps.ai.gateway import gateway
from apps.ai.providers import llm_configured, register_fake_output
from apps.succession.agent4 import SuccessionAnalyzerNotConfiguredError
from apps.succession.agent4 import SuccessionAnalyzerProvider as _BaseSuccessionAnalyzerProvider

AGENT_CODE = "agent4"
SCHEMA = {"narrative": str}


class SuccessionAnalyzerProvider(_BaseSuccessionAnalyzerProvider):
    """LangGraph-backed Agent 4, gateway-fronted. ``configured`` follows the LLM
    gateway so production stays 503 until a provider is wired."""

    @property
    def configured(self) -> bool:  # type: ignore[override]
        return llm_configured()

    def analyze(self, *, critical_role, plan) -> dict:
        from apps.succession import engine

        # Deterministic baseline (internal CycleScore-derived signals only).
        analysis = engine.compute_analysis(critical_role)
        prompt = (
            "Write a brief succession narrative + any additional risk flags from "
            f"this analysis (no individual names): {analysis}"
        )
        result = gateway.run(
            tenant=critical_role.tenant_id, agent_code=AGENT_CODE, prompt=prompt,
            model="succession", schema=SCHEMA,
        )
        if result.status == "NOT_CONFIGURED":
            raise SuccessionAnalyzerNotConfiguredError("Agent 4 (Succession) is not configured.")
        if not result.ok:
            raise RuntimeError(f"Agent 4 unavailable: {result.status}")

        red_flags = list(analysis["red_flags"])
        red_flags.append({"code": "AI_NARRATIVE", "detail": result.content["narrative"]})
        return {
            "ranked_bench": analysis["ranked_bench"],
            "coverage_status": analysis["coverage_status"],
            "red_flags": red_flags,
            "confidence_score": result.confidence,
        }


def _fake(prompt, model):
    return {"narrative": "Coverage is adequate; develop the ready-soon bench toward ready-now."}


register_fake_output(AGENT_CODE, _fake)
