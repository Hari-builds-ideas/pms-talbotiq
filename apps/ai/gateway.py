"""
The LLMGateway — the SINGLE choke for every LLM call (CLAUDE.md rule 6: all LLM
calls go through here, never a direct SDK call). On EVERY call it:

  1. resolves the provider (``settings.LLM_PROVIDER``) — unconfigured → a structured
     ``NOT_CONFIGURED`` result (never a raw exception);
  2. enforces the per-tenant agent budget via ``check_and_reserve_budget`` (M11)
     BEFORE the call — over budget → a ``BUDGET_EXCEEDED`` result;
  3. PII-scrubs the prompt (Doc 3 §5);
  4. calls the provider inside a LangSmith trace span (no-op until configured);
  5. records usage to the ``TokenLedger`` (M11);
  6. validates the output against the agent's schema — malformed → ``SCHEMA_INVALID``;
  7. attaches a confidence score + a low-confidence flag (< floor).

It NEVER raises to its caller — it returns a structured :class:`GatewayResult`, so
a provider/network failure can never crash an agent or fabricate output.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from apps.billing.exceptions import BudgetExceeded
from apps.billing.services import check_and_reserve_budget, record_usage

from .exceptions import LLMNotConfiguredError
from .pii import scrub
from .providers import get_llm_provider
from .schemas import validate_shape
from .tracing import trace

logger = logging.getLogger("pms.ai.gateway")

DEFAULT_CONFIDENCE_FLOOR = 0.70


@dataclass
class GatewayResult:
    status: str  # OK | NOT_CONFIGURED | BUDGET_EXCEEDED | SCHEMA_INVALID | PROVIDER_ERROR
    content: dict | None = None
    confidence: float | None = None
    model: str | None = None
    usage: dict | None = None
    errors: list = field(default_factory=list)
    low_confidence: bool = False

    @property
    def ok(self) -> bool:
        return self.status == "OK"


class LLMGateway:
    """The one place LLM calls flow through. Stateless; instantiate per call or use
    the module-level :data:`gateway`."""

    def run(
        self, *, tenant, agent_code, prompt, model="default", schema=None,
        confidence_floor=DEFAULT_CONFIDENCE_FLOOR,
    ) -> GatewayResult:
        provider = get_llm_provider()
        if not getattr(provider, "configured", False):
            return GatewayResult(status="NOT_CONFIGURED")

        # 2. Budget BEFORE the call (per-tenant; over budget → 429-class result).
        try:
            check_and_reserve_budget(tenant, agent_code)
        except BudgetExceeded as exc:
            return GatewayResult(status="BUDGET_EXCEEDED", errors=[exc.detail])

        # 3. PII-scrub the prompt before it ever reaches the provider.
        scrubbed = scrub(prompt)

        # 4. Provider call inside a trace span.
        try:
            with trace(agent_code, model=model):
                raw = provider.generate(agent_code=agent_code, prompt=scrubbed, model=model)
        except LLMNotConfiguredError:
            return GatewayResult(status="NOT_CONFIGURED")
        except Exception:  # noqa: BLE001 — never crash/fabricate; surface a result
            logger.error("LLM provider failed for agent=%s", agent_code, exc_info=True)
            return GatewayResult(status="PROVIDER_ERROR")

        content = raw.get("content") or {}
        used_model = raw.get("model", model)
        prompt_tokens = int(raw.get("prompt_tokens", 0))
        completion_tokens = int(raw.get("completion_tokens", 0))
        confidence = float(raw.get("confidence", 1.0))

        # 5. Meter usage (the TokenLedger the budget reads against).
        record_usage(
            tenant,
            agent_code=agent_code,
            model=used_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

        # 6. Validate the structured output against the agent's schema.
        if schema is not None:
            ok, errors = validate_shape(content, schema)
            if not ok:
                return GatewayResult(
                    status="SCHEMA_INVALID", content=content, errors=errors,
                    confidence=confidence, model=used_model, usage=usage,
                )

        # 7. Confidence + low-confidence flag.
        return GatewayResult(
            status="OK", content=content, confidence=confidence, model=used_model,
            usage=usage, low_confidence=confidence < confidence_floor,
        )


#: Module-level singleton for convenience.
gateway = LLMGateway()
