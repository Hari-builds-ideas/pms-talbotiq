"""
AI / LLM gateway exceptions. The gateway itself NEVER raises these to its caller —
it returns a structured ``GatewayResult`` (status) instead (CLAUDE.md: "surface
errors as structured results, never raw exceptions to the caller"). These types are
used internally and by the providers.
"""


class LLMNotConfiguredError(RuntimeError):
    """No real LLM provider is wired (production default). Agents surface 503; the
    gateway converts this into a ``NOT_CONFIGURED`` result rather than raising."""


class LLMProviderError(RuntimeError):
    """A real provider failed at call time (network / bad response). The gateway
    converts this into a ``PROVIDER_ERROR`` result; no output is fabricated."""


class LLMGlobalCeilingError(LLMProviderError):
    """The process-shared GLOBAL call ceiling (``settings.LLM_MAX_CALLS``) was hit —
    a deliberate cost backstop, NOT a provider failure. The gateway maps this to a
    ``BUDGET_EXCEEDED`` result (refunding the per-tenant reservation), so the async
    seam DEGRADES (not FAILS) and the sync chat path returns 429 (not 503) — i.e. a
    graceful "run ceiling reached", never a misleading hard error (audit Finding A).

    Subclasses :class:`LLMProviderError` so a provider that lets it propagate, and
    any ``except LLMProviderError`` / ``pytest.raises(LLMProviderError)`` already in
    place, keep working — the gateway catches it FIRST (before the generic handler)
    to apply the graceful mapping."""


class AgentUnavailable(LLMProviderError):
    """A gateway-fronted agent could not serve because the GatewayResult was not
    ``OK`` (and not ``NOT_CONFIGURED``, which agents raise as their own
    NotConfigured error). Carries the structured ``gateway_status`` so the async
    seam task can distinguish a graceful DEGRADE (``BUDGET_EXCEEDED`` — over
    budget / global ceiling) from a hard FAIL (``PROVIDER_ERROR`` /
    ``SCHEMA_INVALID``).

    Subclasses ``RuntimeError`` so existing broad ``except Exception`` handlers
    (and ``pytest.raises(RuntimeError)``) keep working unchanged."""

    def __init__(self, gateway_status: str, message: str | None = None):
        self.gateway_status = gateway_status
        super().__init__(message or gateway_status)
