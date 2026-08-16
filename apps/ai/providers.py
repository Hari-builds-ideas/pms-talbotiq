"""
The LLM provider layer — provider-agnostic per CLAUDE.md (no hardcoded vendor).

* ``LLMProvider`` — the ABC every provider implements.
* ``NotConfiguredProvider`` — the DEFAULT (no ``LLM_PROVIDER`` set). ``configured``
  is False, so every agent surfaces a loud 503 in production and NOTHING is ever
  fabricated. This is the production state until Hari wires a key
  (NEEDS_HARI_llm_provider.md).
* ``FakeLLMProvider`` — deterministic, in-repo, for TESTS + demos. It dispatches to
  a per-agent output builder (registered via ``register_fake_output``), so the full
  agent graphs run end-to-end with NO network call and reproducible output.
* ``HTTPLLMProvider`` — a thin OpenAI-compatible adapter SCAFFOLD reading base-url +
  key from env. INERT without a key (raises), and never called tonight; the real
  SDK swap is documented in NEEDS_HARI_llm_provider.md.

``get_llm_provider()`` resolves ``settings.LLM_PROVIDER`` (an import string),
defaulting to ``NotConfiguredProvider``.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from django.conf import settings
from django.utils.module_loading import import_string

from .exceptions import LLMNotConfiguredError, LLMProviderError

logger = logging.getLogger("pms.ai.providers")


class LLMProvider(ABC):
    """Provider contract. ``generate`` returns a dict:
    ``{"content": <dict>, "model": str, "prompt_tokens": int,
       "completion_tokens": int, "confidence": float}``."""

    configured: bool = True
    name: str = "base"

    @abstractmethod
    def generate(self, *, agent_code: str, prompt: str, model: str) -> dict:
        raise NotImplementedError


class NotConfiguredProvider(LLMProvider):
    """Default: no LLM wired. Any call raises; ``configured`` is False so callers
    short-circuit to 503 before ever calling."""

    configured = False
    name = "not_configured"

    def generate(self, *, agent_code, prompt, model) -> dict:
        raise LLMNotConfiguredError(
            "No LLM provider configured (set LLM_PROVIDER + a key — Module 10 "
            "production step). Agents surface 503 until then; nothing is fabricated."
        )


# ── deterministic fake (tests + demos) ────────────────────────────────────────

#: agent_code -> builder(prompt, model) -> content dict. Agents register here so
#: their fake output is co-located with the agent + deterministic.
_FAKE_OUTPUTS: dict[str, callable] = {}
#: agent_code -> confidence to report (default 0.9). Tests tweak to exercise the
#: low-confidence (< 0.70) warning path.
_FAKE_CONFIDENCE: dict[str, float] = {}


def register_fake_output(agent_code: str, builder) -> None:
    _FAKE_OUTPUTS[agent_code] = builder


def set_fake_confidence(agent_code: str, confidence: float) -> None:
    _FAKE_CONFIDENCE[agent_code] = confidence


class FakeLLMProvider(LLMProvider):
    """Deterministic provider for tests/demos. Returns the agent's registered fake
    content (or a generic echo), with stable token counts + confidence. NO network."""

    configured = True
    name = "fake"

    def generate(self, *, agent_code, prompt, model) -> dict:
        builder = _FAKE_OUTPUTS.get(agent_code)
        content = builder(prompt, model) if builder else {"text": f"[fake:{agent_code}]"}
        return {
            "content": content,
            "model": model or "fake-llm-1",
            "prompt_tokens": min(len(prompt), 4000),
            "completion_tokens": 128,
            "confidence": _FAKE_CONFIDENCE.get(agent_code, 0.9),
        }

    #: A queue of turns for :meth:`generate_with_tools`, set by a test. Each entry is
    #: either ``{"tool_calls": [...]}`` or ``{"content": "..."}``. Scripting the model
    #: is the only way to test the LOOP itself — whether tools get run with the trusted
    #: context, whether denials come back, whether the iteration cap holds — without the
    #: assertions depending on what a real model felt like doing that minute.
    script: list = []

    def generate_with_tools(self, *, agent_code, messages, tools, model) -> dict:
        turn = self.script.pop(0) if self.script else {"content": "[fake: no script left]"}
        return {
            "content": turn.get("content") or "",
            "tool_calls": turn.get("tool_calls") or [],
            "finish_reason": "stop",
            "model": model or "fake-llm-1",
            "prompt_tokens": 100,
            "completion_tokens": 20,
        }


# ── inert real adapter scaffold (never called tonight) ────────────────────────


class HTTPLLMProvider(LLMProvider):
    """OpenAI-compatible HTTP adapter SCAFFOLD. Reads base-url + key from env; INERT
    without them (raises). Wired but never called tonight — the real provider/SDK +
    key land per NEEDS_HARI_llm_provider.md."""

    name = "http"

    def __init__(self):
        import os

        self.base_url = os.environ.get("LLM_BASE_URL", "")
        self.api_key = os.environ.get("LLM_API_KEY", "")

    @property
    def configured(self) -> bool:  # type: ignore[override]
        return bool(self.base_url and self.api_key)

    def generate(self, *, agent_code, prompt, model) -> dict:
        if not self.configured:
            raise LLMNotConfiguredError("HTTPLLMProvider has no LLM_BASE_URL/LLM_API_KEY.")
        # Production: POST to the OpenAI-compatible /chat/completions here and parse
        # the structured result. Deliberately unimplemented tonight (no key, no
        # network) — see NEEDS_HARI_llm_provider.md.
        raise LLMProviderError(
            "HTTPLLMProvider.generate is not implemented in the MVP (no real key "
            "tonight); configure a provider per NEEDS_HARI_llm_provider.md."
        )


def get_llm_provider(tenant=None) -> LLMProvider:
    """Resolve the LLM provider for ``tenant``.

    Order (B1): the tenant's own provider + key → the deployment's
    ``settings.LLM_PROVIDER`` + environment key → :class:`NotConfiguredProvider`.

    With no tenant this is the old behaviour exactly, so every existing caller and
    test is unaffected. With a tenant that has stored its own key, the provider is
    constructed with that key instead of the environment's — which is the whole
    point of per-tenant configuration: a customer brings their own key without a
    redeploy, and their spend is theirs.
    """
    if tenant is not None:
        try:
            from .tenant_config import resolve_provider

            dotted, api_key, _source = resolve_provider(tenant)
            if dotted:
                return _instantiate(dotted, api_key)
        except Exception:  # noqa: BLE001 — a bad row must not break AI entirely
            logger.exception("Tenant AI config lookup failed; using the environment provider")

    dotted = getattr(settings, "LLM_PROVIDER", "apps.ai.providers.NotConfiguredProvider")
    return _instantiate(dotted, None)


def _instantiate(dotted: str, api_key: str | None) -> LLMProvider:
    """Build a provider, passing an explicit key only when we have one.

    Providers that predate per-tenant keys take no arguments, so the keyword is
    only offered when it is needed and a TypeError falls back to the plain
    constructor rather than failing the request.
    """
    cls = import_string(dotted)
    if api_key:
        try:
            return cls(api_key=api_key)
        except TypeError:
            logger.warning(
                "%s does not accept a per-tenant api_key; falling back to its "
                "environment configuration.", dotted,
            )
    return cls()


def llm_configured() -> bool:
    """True iff a real (configured) LLM provider is wired. Agents delegate their
    own ``configured`` to this, so pointing a seam at an agent provider is SAFE in
    production: it reports unconfigured (→ 503) until ``LLM_PROVIDER`` is set."""
    try:
        return bool(getattr(get_llm_provider(), "configured", False))
    except Exception:  # noqa: BLE001 - a bad setting must not crash the gate
        return False
