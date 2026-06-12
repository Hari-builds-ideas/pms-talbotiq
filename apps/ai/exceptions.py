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
