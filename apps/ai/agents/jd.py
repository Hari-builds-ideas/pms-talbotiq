"""
JD Generator (Large). Fills the Module-6 ``JDGeneratorProvider`` seam: validated
inputs → gateway LLM JD body → structure. The Module-6 lifecycle locks the result
``source=AI`` PENDING_HUMAN_REVIEW (a generated JD is never published directly).
``configured`` follows the gateway (prod 503). Surface is entitlement-gated with
``jd_generator`` (FULL_AI) at go-live — see NEEDS_HARI_llm_provider.md.
"""
from __future__ import annotations

import json

from apps.ai.gateway import gateway
from apps.ai.providers import llm_configured, register_fake_output
from apps.ai.schemas import NonEmpty
from apps.jd.generator import JDGeneratorNotConfiguredError
from apps.jd.generator import JDGeneratorProvider as _BaseJDGeneratorProvider

AGENT_CODE = "jd_generator"
#: Tightened: a real summary + the three lists must all be present (an empty
#: summary or a missing list fails validation rather than passing a hollow JD).
SCHEMA = {
    "body": {
        "summary": NonEmpty(20),
        "responsibilities": list,
        "must_haves": list,
        "nice_to_haves": list,
    }
}


class JDGeneratorProvider(_BaseJDGeneratorProvider):
    @property
    def configured(self) -> bool:  # type: ignore[override]
        return llm_configured()

    def generate(self, *, jd, inputs) -> dict:
        prompt = (
            f"Generate a job-description body for the role '{jd.title}' "
            f"(level {jd.level}, {jd.department or 'unspecified'} dept) from this "
            f"structured brief: {json.dumps(inputs)}.\n"
            "Pull the real responsibilities and must-haves from the brief — tight "
            "and role-specific, no generic boilerplate. Return summary, "
            "responsibilities, must_haves, nice_to_haves."
        )
        result = gateway.run(
            tenant=jd.tenant_id, agent_code=AGENT_CODE, prompt=prompt, model="jd", schema=SCHEMA
        )
        if result.status == "NOT_CONFIGURED":
            raise JDGeneratorNotConfiguredError("JD Generator is not configured.")
        if not result.ok:
            raise RuntimeError(f"JD Generator unavailable: {result.status}")
        return {
            "body": result.content["body"],
            "confidence_score": result.confidence,
            "citations": [{"type": "inputs_snapshot"}],
        }


def _fake(prompt, model):
    return {
        "body": {
            "summary": "Owns the analytics data models and pipelines.",
            "responsibilities": ["Build + maintain dbt models", "Partner with stakeholders"],
            "must_haves": ["3+ yrs analytics engineering", "SQL + dbt"],
            "nice_to_haves": ["Python", "BI tooling"],
        }
    }


register_fake_output(AGENT_CODE, _fake)
