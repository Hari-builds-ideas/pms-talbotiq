"""
The Google Gemini LLM provider — a sibling of :mod:`apps.ai.openai_provider`.

Gemini ships an **OpenAI-compatible** Chat Completions endpoint
(``https://generativelanguage.googleapis.com/v1beta/openai``), so the gateway pipeline
(budget → PII-scrub → call → schema-validate → meter → confidence → PENDING) is byte-for-byte
unchanged from the OpenAI path — only the base URL, the key (``GEMINI_API_KEY``), and the model
names differ. This is the free-tier provider for the demo deploy (V1_C): Gemini's free tier
serves the AI on the key Hari pastes into the Render dashboard.

Model resolution: the per-agent ``settings.LLM_MODEL_MAP`` values are OpenAI names (gpt-4o…),
which Gemini won't accept — so this provider maps every logical agent to a Gemini model, using
``settings.GEMINI_MODEL`` (default ``gemini-1.5-flash`` — fast + free-tier friendly). Override per
env if you want a stronger model for human-read agents.

Unset key → ``configured`` False, so every agent stays on the graceful 503 path and NOTHING is
fabricated. Any failure raises ``LLMProviderError`` (gateway → PROVIDER_ERROR).
"""
from __future__ import annotations

import json
import logging
import time

import requests
from django.conf import settings

from apps.billing import atomic

from .agent_config import system_prompt_for
from .exceptions import LLMGlobalCeilingError, LLMProviderError
from .providers import LLMProvider

logger = logging.getLogger("pms.ai.gemini")

_GLOBAL_CALL_KEY = "llm:global:calls"
#: Gemini's OpenAI-compatible base (Chat Completions).
_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
#: Free-tier-friendly default; override via settings.GEMINI_MODEL.
_DEFAULT_MODEL = "gemini-1.5-flash"


def _model_for(logical: str) -> str:
    """Resolve any logical agent name to a Gemini model id. If ``LLM_MODEL_MAP`` already
    holds a Gemini name (starts with ``gemini``) use it; otherwise use ``GEMINI_MODEL``."""
    mapped = (getattr(settings, "LLM_MODEL_MAP", {}) or {}).get(logical) or ""
    if mapped.startswith("gemini"):
        return mapped
    return getattr(settings, "GEMINI_MODEL", "") or _DEFAULT_MODEL


class GeminiProvider(LLMProvider):
    """Google Gemini via its OpenAI-compatible Chat Completions endpoint (JSON mode)."""

    name = "gemini"

    def __init__(self):
        self.base_url = (
            getattr(settings, "GEMINI_BASE_URL", "") or _DEFAULT_BASE_URL
        ).rstrip("/")
        # Accept GEMINI_API_KEY or the generic LLM_API_KEY (never hardcoded).
        self.api_key = getattr(settings, "GEMINI_API_KEY", "") or getattr(
            settings, "LLM_API_KEY", ""
        )
        self.timeout = float(getattr(settings, "LLM_TIMEOUT_SECONDS", 30))
        self.max_tokens = int(getattr(settings, "LLM_MAX_TOKENS", 900))
        self.global_ceiling = int(getattr(settings, "LLM_MAX_CALLS", 0))

    @property
    def configured(self) -> bool:  # type: ignore[override]
        return bool(self.api_key)

    # ── global run ceiling (quota guard — matters on any metered tier) ──────────
    def _reserve_global(self) -> None:
        if self.global_ceiling <= 0:
            return
        try:
            count = atomic.incr_window(_GLOBAL_CALL_KEY, ttl_ms=24 * 3600 * 1000)
        except Exception:  # noqa: BLE001 — a cache miss must not wedge the call
            return
        if count > self.global_ceiling:
            raise LLMGlobalCeilingError(
                f"Global LLM call ceiling ({self.global_ceiling}) reached for this "
                "run — refusing further calls to protect the quota."
            )

    # ── provider contract ─────────────────────────────────────────────────────
    def generate(self, *, agent_code: str, prompt: str, model: str) -> dict:
        if not self.configured:
            raise LLMProviderError("GeminiProvider has no API key.")
        self._reserve_global()

        gemini_model = _model_for(model)
        system = system_prompt_for(agent_code)
        # JSON-mode guard: ensure the literal "json" is present (parity with the OpenAI
        # path; harmless if the endpoint doesn't require it).
        if "json" not in f"{system}\n{prompt}".lower():
            system = f"{system}\nRespond with a single JSON object and nothing else."

        payload = {
            "model": gemini_model,
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
            raise LLMProviderError("Gemini returned non-JSON content.")

        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))

        confidence = 0.88
        if finish == "length":
            confidence = 0.6

        return {
            "content": content,
            "model": gemini_model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "confidence": confidence,
        }

    def _post_with_backoff(self, url, payload, headers, *, attempts=3) -> dict:
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                resp = requests.post(
                    url, json=payload, headers=headers,
                    timeout=(min(self.timeout, 10.0), self.timeout),
                )
            except requests.RequestException as exc:
                last_exc = exc
                time.sleep(1.5 * (attempt + 1))
                continue
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 2.0 * (attempt + 1)
                logger.warning("Gemini 429; backing off %.1fs (attempt %d)", delay, attempt + 1)
                time.sleep(min(delay, 10.0))
                last_exc = LLMProviderError("Gemini rate limit (429).")
                continue
            if resp.status_code >= 400:
                # Don't leak the body (could echo the prompt); log status only.
                logger.error("Gemini error status=%s", resp.status_code)
                raise LLMProviderError(f"Gemini HTTP {resp.status_code}.")
            return resp.json()
        raise last_exc or LLMProviderError("Gemini call failed after retries.")
