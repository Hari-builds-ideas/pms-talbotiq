"""
The OpenAI LLM provider (OpenAI Chat Completions, JSON mode).

A sibling of :mod:`apps.ai.groq` — same gateway contract, same OpenAI-compatible
Chat Completions request/response shape, so the gateway pipeline (budget → PII-scrub
→ call → schema-validate → meter → confidence → PENDING) is unchanged. Differences
from Groq are only: the base URL (``https://api.openai.com/v1``), the key
(``OPENAI_API_KEY``), the model map (real OpenAI models), and a JSON-mode guard —
OpenAI's ``response_format=json_object`` 400s unless the word "json" appears in the
messages (our agent prompts already say "JSON"; the guard makes that robust against
a custom system-prompt override).

Safety (OpenAI is PAID per token, not a free tier):
  * a per-agent ``model`` map (``settings.LLM_MODEL_MAP``) — a strong model for the
    human-read agents, a fast/cheap one for chat/default;
  * the process-shared GLOBAL call ceiling (``settings.LLM_MAX_CALLS``, cache-counted)
    so a runaway loop / seed smoke can never burn the quota;
  * bounded ``max_tokens``; honour 429 ``Retry-After`` with a couple of backoffs.

Unset key → ``configured`` False, so every agent stays on the graceful 503 path and
NOTHING is fabricated. Any failure raises ``LLMProviderError`` (gateway → PROVIDER_ERROR).
"""
from __future__ import annotations

import json
import logging
import time

import requests
from django.conf import settings

from apps.billing import atomic

from .agent_config import system_prompt_for
from .exceptions import LLMProviderError
from .providers import LLMProvider

logger = logging.getLogger("pms.ai.openai")

_GLOBAL_CALL_KEY = "llm:global:calls"
#: Fallback when LLM_MODEL_MAP lacks the logical name AND a 'default' — a cheap model.
_FALLBACK_MODEL = "gpt-4o-mini"


def _model_for(logical: str) -> str:
    """Resolve a logical model name (e.g. 'review', 'chat') to an OpenAI model id via
    ``settings.LLM_MODEL_MAP``, falling back to the map's 'default' then a cheap model."""
    mapping = getattr(settings, "LLM_MODEL_MAP", {}) or {}
    return mapping.get(logical) or mapping.get("default") or _FALLBACK_MODEL


class OpenAIProvider(LLMProvider):
    """OpenAI Chat Completions adapter (JSON mode)."""

    name = "openai"

    def __init__(self):
        self.base_url = (
            getattr(settings, "OPENAI_BASE_URL", "")
            or "https://api.openai.com/v1"
        ).rstrip("/")
        # Accept OPENAI_API_KEY or the generic LLM_API_KEY (never hardcoded).
        self.api_key = getattr(settings, "OPENAI_API_KEY", "") or getattr(
            settings, "LLM_API_KEY", ""
        )
        self.timeout = float(getattr(settings, "LLM_TIMEOUT_SECONDS", 30))
        self.max_tokens = int(getattr(settings, "LLM_MAX_TOKENS", 900))
        self.global_ceiling = int(getattr(settings, "LLM_MAX_CALLS", 0))

    @property
    def configured(self) -> bool:  # type: ignore[override]
        return bool(self.api_key)

    # ── global run ceiling (quota guard — matters more on paid pricing) ────────
    def _reserve_global(self) -> None:
        if self.global_ceiling <= 0:
            return
        try:
            # ATOMIC fixed-window INCR: concurrent callers across replicas can't
            # overshoot the global ceiling at the edge.
            count = atomic.incr_window(_GLOBAL_CALL_KEY, ttl_ms=24 * 3600 * 1000)
        except Exception:  # noqa: BLE001 — a cache miss must not wedge the call
            return
        if count > self.global_ceiling:
            raise LLMProviderError(
                f"Global LLM call ceiling ({self.global_ceiling}) reached for this "
                "run — refusing further calls to protect the quota."
            )

    # ── provider contract ─────────────────────────────────────────────────────
    def generate(self, *, agent_code: str, prompt: str, model: str) -> dict:
        if not self.configured:
            raise LLMProviderError("OpenAIProvider has no API key.")
        self._reserve_global()

        openai_model = _model_for(model)
        system = system_prompt_for(agent_code)
        # JSON-mode guard: OpenAI requires the literal "json" somewhere in the
        # messages when response_format is json_object. Our prompts already say
        # "JSON"; append a one-liner only if a custom prompt omitted it.
        if "json" not in f"{system}\n{prompt}".lower():
            system = f"{system}\nRespond with a single JSON object and nothing else."

        payload = {
            "model": openai_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"

        data = self._post_with_backoff(url, payload, headers)

        choice = (data.get("choices") or [{}])[0]
        finish = choice.get("finish_reason")
        raw_content = (choice.get("message") or {}).get("content") or "{}"
        try:
            content = json.loads(raw_content)
        except (json.JSONDecodeError, TypeError):
            # The model broke JSON mode — do NOT fabricate; surface a provider error
            # so the gateway returns a structured failure (no draft).
            raise LLMProviderError("OpenAI returned non-JSON content.")

        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))

        # Confidence heuristic (OpenAI has no native score): start high, penalise a
        # truncated completion. Calibrated so a clean answer sits above the 0.70 floor.
        confidence = 0.88
        if finish == "length":
            confidence = 0.6

        return {
            "content": content,
            "model": openai_model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "confidence": confidence,
        }

    def _post_with_backoff(self, url, payload, headers, *, attempts=3) -> dict:
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
            except requests.RequestException as exc:
                last_exc = exc
                time.sleep(1.5 * (attempt + 1))
                continue
            if resp.status_code == 429:
                # Rate-limit (or quota). Honour Retry-After, then retry a couple of
                # times; a hard insufficient-quota 429 falls through to the error.
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 2.0 * (attempt + 1)
                logger.warning("OpenAI 429; backing off %.1fs (attempt %d)", delay, attempt + 1)
                time.sleep(min(delay, 10.0))
                last_exc = LLMProviderError("OpenAI rate limit (429).")
                continue
            if resp.status_code >= 400:
                # Don't leak the body (could echo the prompt); log status only.
                logger.error("OpenAI error status=%s", resp.status_code)
                raise LLMProviderError(f"OpenAI HTTP {resp.status_code}.")
            return resp.json()
        raise last_exc or LLMProviderError("OpenAI call failed after retries.")
