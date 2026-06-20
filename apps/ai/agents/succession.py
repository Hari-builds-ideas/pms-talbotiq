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

import json

from apps.ai.evidence import confidence_with_sufficiency, succession_evidence
from apps.ai.gateway import gateway
from apps.ai.exceptions import AgentUnavailable
from apps.ai.providers import llm_configured, register_fake_output
from apps.ai.schemas import NonEmpty
from apps.succession.agent4 import SuccessionAnalyzerNotConfiguredError
from apps.succession.agent4 import SuccessionAnalyzerProvider as _BaseSuccessionAnalyzerProvider

AGENT_CODE = "agent4"
#: Tightened: a real narrative (>= 40 chars), not a blank/one-word string.
SCHEMA = {"narrative": NonEmpty(40)}


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
        # Name-free evidence: bench depth + readiness/band distribution + coverage
        # + red-flag codes — never candidate ids/emails (defence in depth).
        ev = succession_evidence(analysis)
        prompt = (
            "Write a crisp, decision-useful succession narrative for HR leadership "
            "from this deterministic analysis (NO individual names — reason about "
            "coverage and bench depth):\n"
            f"Bench size: {ev['bench_size']}.\n"
            f"Readiness distribution: {json.dumps(ev['readiness_distribution'])}.\n"
            f"Performance-band spread: {json.dumps(ev['performance_band_distribution'])}.\n"
            f"Coverage status: {ev['coverage_status']}.\n"
            f"Red-flag codes: {json.dumps(ev['red_flag_codes'])}.\n"
            "Lead with the coverage picture, name the key gap, and give the single "
            "most important development action."
        )
        result = gateway.run(
            tenant=critical_role.tenant_id, agent_code=AGENT_CODE, prompt=prompt,
            model="succession", schema=SCHEMA,
        )
        if result.status == "NOT_CONFIGURED":
            raise SuccessionAnalyzerNotConfiguredError("Agent 4 (Succession) is not configured.")
        if not result.ok:
            raise AgentUnavailable(result.status, f"Agent 4 unavailable: {result.status}")

        red_flags = list(analysis["red_flags"])
        red_flags.append({"code": "AI_NARRATIVE", "detail": result.content["narrative"]})
        return {
            "ranked_bench": analysis["ranked_bench"],
            "coverage_status": analysis["coverage_status"],
            "red_flags": red_flags,
            "confidence_score": confidence_with_sufficiency(
                result.confidence, ev["evidence_sufficiency"]
            ),
        }


def _fake(prompt, model):
    return {"narrative": "Coverage is adequate; develop the ready-soon bench toward ready-now."}


register_fake_output(AGENT_CODE, _fake)
