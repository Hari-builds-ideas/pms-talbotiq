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
from apps.billing.services import check_and_reserve_budget, record_usage, release_budget

from .tenant_switch import ai_enabled_for

from .exceptions import LLMGlobalCeilingError, LLMNotConfiguredError
from .pii import scrub
from .providers import get_llm_provider
from .schemas import validate_shape
from .tracing import trace

logger = logging.getLogger("pms.ai.gateway")

DEFAULT_CONFIDENCE_FLOOR = 0.70

#: Carried in ``GatewayResult.errors`` when the tenant has switched AI off, so the
#: "administrator turned this off" case is distinguishable from "no provider key".
AI_DISABLED_DETAIL = "AI is switched off for this organisation."


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
        # 0. The tenant's own AI switch, checked before anything else.
        #
        # Distinct from the entitlement: the plan says what a tenant MAY use, this
        # says what they WANT enabled. An organisation with a policy against sending
        # employee data to a model provider needs an off switch that does not require
        # a downgrade, and it has to bind HERE rather than in the UI — hiding the
        # buttons leaves every endpoint reachable.
        #
        # Reported as NOT_CONFIGURED rather than a new status on purpose. A dozen call
        # sites already branch on it and degrade cleanly — 503, DEGRADED job, honest
        # "assistant unavailable", never fabricated output. A new status would be
        # unhandled in most of them, which is how an off switch turns into a 500. The
        # reason travels in `errors` for anyone who needs to tell the two apart.
        if not ai_enabled_for(tenant):
            return GatewayResult(status="NOT_CONFIGURED", errors=[AI_DISABLED_DETAIL])

        # Resolved PER TENANT (B1): the tenant's own key wins, then the
        # environment key, then not configured. Passing the tenant is what makes a
        # customer-supplied key take effect without a redeploy.
        provider = get_llm_provider(tenant)
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
            # Reserved but the provider couldn't serve — refund (no real usage).
            release_budget(tenant, agent_code)
            return GatewayResult(status="NOT_CONFIGURED")
        except LLMGlobalCeilingError as exc:
            # The global cost backstop fired — a graceful limit, NOT a provider
            # failure (audit Finding A). Refund the reservation (no real call) and
            # surface BUDGET_EXCEEDED so the async seam DEGRADES and chat returns 429
            # ("run ceiling reached"), never PROVIDER_ERROR → FAILED / 503.
            release_budget(tenant, agent_code)
            return GatewayResult(status="BUDGET_EXCEEDED", errors=[str(exc)])
        except Exception:  # noqa: BLE001 — never crash/fabricate; surface a result
            logger.error("LLM provider failed for agent=%s", agent_code, exc_info=True)
            # Reserved but the call failed before metering — refund the reservation.
            release_budget(tenant, agent_code)
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


    # ── function-calling turn (AGENT_V3/B) ────────────────────────────────────
    def run_tools(self, *, tenant, agent_code, messages, tools, model="default"):
        """One turn of a TOOL-CALLING conversation, through the same choke point.

        A sibling of :meth:`run`, not a replacement: budget, PII-scrub, tracing and
        metering all still apply, because CLAUDE.md rule 6 says every LLM call goes
        through the gateway and a tool-calling call is still an LLM call. Skipping it
        would mean an agent that silently spends unmetered tokens.

        Two deliberate differences from :meth:`run`:

        * **Only the user-authored text is scrubbed.** Tool RESULTS come from our own
          scoped queries, and scrubbing them would corrupt the very numbers the answer
          depends on — a redacted score is worse than no score. The PII risk is in what
          the user types, which is what we clean.
        * **No schema validation.** The output is either typed ``tool_calls`` or prose
          for a human; there is no JSON contract to check.

        Returns a :class:`GatewayResult` whose ``content`` is
        ``{"text": …, "tool_calls": […]}``.
        """
        # The tenant switch again — this is the OTHER way out to a provider, and a
        # kill switch that covers one of two doors is not a kill switch.
        if not ai_enabled_for(tenant):
            return GatewayResult(status="NOT_CONFIGURED", errors=[AI_DISABLED_DETAIL])

        # Resolved PER TENANT (B1): the tenant's own key wins, then the
        # environment key, then not configured. Passing the tenant is what makes a
        # customer-supplied key take effect without a redeploy.
        provider = get_llm_provider(tenant)
        if not getattr(provider, "configured", False):
            return GatewayResult(status="NOT_CONFIGURED")
        if not hasattr(provider, "generate_with_tools"):
            # An older provider can't do this; degrade honestly rather than crash so the
            # caller falls back to the pre-existing answer path.
            return GatewayResult(status="NOT_CONFIGURED",
                                 errors=["provider has no tool-calling support"])

        try:
            check_and_reserve_budget(tenant, agent_code)
        except BudgetExceeded as exc:
            return GatewayResult(status="BUDGET_EXCEEDED", errors=[exc.detail])

        cleaned = [_scrub_user_text(m) for m in messages]

        try:
            with trace(agent_code, model=model):
                raw = provider.generate_with_tools(
                    agent_code=agent_code, messages=cleaned, tools=tools, model=model)
        except LLMNotConfiguredError:
            release_budget(tenant, agent_code)
            return GatewayResult(status="NOT_CONFIGURED")
        except LLMGlobalCeilingError as exc:
            release_budget(tenant, agent_code)
            return GatewayResult(status="BUDGET_EXCEEDED", errors=[str(exc)])
        except Exception:  # noqa: BLE001 — never crash the request, never fabricate
            logger.error("LLM tool call failed for agent=%s", agent_code, exc_info=True)
            release_budget(tenant, agent_code)
            return GatewayResult(status="PROVIDER_ERROR")

        prompt_tokens = int(raw.get("prompt_tokens", 0))
        completion_tokens = int(raw.get("completion_tokens", 0))
        used_model = raw.get("model", model)
        record_usage(tenant, agent_code=agent_code, model=used_model,
                     prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
        return GatewayResult(
            status="OK",
            content={"text": raw.get("content") or "", "tool_calls": raw.get("tool_calls") or []},
            model=used_model,
            usage={"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                   "total_tokens": prompt_tokens + completion_tokens},
        )


def _scrub_user_text(message):
    """Scrub only what a HUMAN wrote. Tool results are our own scoped rows: running a PII
    scrubber over them would mangle the names and numbers the answer is built from."""
    if message.get("role") != "user" or not isinstance(message.get("content"), str):
        return message
    return {**message, "content": scrub(message["content"])}


#: Module-level singleton for convenience.
gateway = LLMGateway()
