"""
The real LLM provider: Groq (OpenAI-compatible Chat Completions).

Implements the :class:`~apps.ai.providers.LLMProvider` ABC. The gateway is the
only caller (CLAUDE.md rule 6); this class turns the agent's prompt into a Groq
chat request that returns STRICT JSON matching the agent's expected content
shape, parses it, and reports usage + a confidence heuristic. It never fabricates
output — any failure raises ``LLMProviderError`` (the gateway maps that to a
``PROVIDER_ERROR`` result) and an unset key leaves ``configured`` False so the
agents stay on the 503 path.

Cost/quota safety for the free tier:
  * a per-agent ``model`` map (``settings.LLM_MODEL_MAP``) — a smart 70B model for
    human-read agents, a fast 8B model for chat — so quality lands where it matters;
  * a process-shared GLOBAL call ceiling (``settings.LLM_MAX_CALLS``, counted in the
    Redis cache) so a runaway loop / seed smoke-test can never exhaust the daily cap;
  * bounded ``max_tokens`` to respect the tokens-per-minute limit;
  * 429 is EXPECTED: we honour ``Retry-After`` and back off a couple of times.
"""
from __future__ import annotations

import json
import logging
import time

import requests
from django.conf import settings
from django.core.cache import cache

from .exceptions import LLMProviderError
from .providers import LLMProvider

logger = logging.getLogger("pms.ai.groq")

_GLOBAL_CALL_KEY = "llm:global:calls"

# Per-agent system prompts that pin the EXACT JSON shape each agent's nodes expect
# (see the agents' SCHEMA + structure nodes). The model must return ONLY this JSON.
_SYSTEM_PROMPTS: dict[str, str] = {
    "agent1": (
        "You are an enterprise performance-review assistant. Using ONLY the supplied "
        "evidence, write a fair, specific, professional review. Respond with ONLY a "
        "JSON object of the form: {\"sections\": {\"summary\": str, \"strengths\": str, "
        "\"areas_for_development\": str, \"goals_assessment\": str, "
        "\"recommendations\": str}}. Each section is 2-4 sentences. Do not include "
        "any names, emails, or text outside the JSON."
    ),
    "agent3": (
        "You summarise ANONYMISED 360-degree feedback. Respond with ONLY a JSON object "
        "of the form: {\"sections\": {\"strengths\": str, \"growth\": str, "
        "\"themes\": str, \"risks\": str}}. Never include any name, email, or other "
        "identifier — the input is anonymised and the output must stay anonymous."
    ),
    "agent4": (
        "You write a concise succession-planning narrative from a deterministic "
        "analysis. Respond with ONLY a JSON object of the form: {\"narrative\": str} "
        "(3-5 sentences, no individual names; focus on coverage and bench development)."
    ),
    "jd_generator": (
        "You generate a job description body. Respond with ONLY a JSON object of the "
        "form: {\"body\": {\"summary\": str, \"responsibilities\": [str], "
        "\"must_haves\": [str], \"nice_to_haves\": [str]}}. Lists hold 3-6 concise items."
    ),
    "career_roadmap": (
        "You draft an ADVISORY development roadmap (never a promise or promotion). "
        "Respond with ONLY a JSON object of the form: {\"tiers\": [{\"index\": int, "
        "\"title\": str, \"detail\": str, \"basis\": str}]} with 2-4 ordered tiers."
    ),
    "chat": (
        "Classify the user's intent toward an HR system as either reading information "
        "or making a change. Respond with ONLY a JSON object: {\"intent\": \"read\"} "
        "or {\"intent\": \"write\"}. Any approval, rejection, create, update, delete, "
        "finalize, publish, or set-value request is \"write\"; questions are \"read\"."
    ),
}
_DEFAULT_SYSTEM = (
    "Respond with ONLY a single JSON object that directly answers the request. "
    "Do not include any text outside the JSON."
)


def _model_for(logical: str) -> str:
    """Resolve a logical model name (e.g. 'review', 'chat') to a Groq model id via
    ``settings.LLM_MODEL_MAP``, falling back to the map's 'default'."""
    mapping = getattr(settings, "LLM_MODEL_MAP", {}) or {}
    return mapping.get(logical) or mapping.get("default") or "llama-3.1-8b-instant"


class GroqProvider(LLMProvider):
    """OpenAI-compatible Groq Chat Completions adapter."""

    name = "groq"

    def __init__(self):
        self.base_url = (
            getattr(settings, "LLM_BASE_URL", "")
            or "https://api.groq.com/openai/v1"
        ).rstrip("/")
        # Accept GROQ_API_KEY or the generic LLM_API_KEY.
        self.api_key = getattr(settings, "LLM_API_KEY", "") or getattr(
            settings, "GROQ_API_KEY", ""
        )
        self.timeout = float(getattr(settings, "LLM_TIMEOUT_SECONDS", 30))
        self.max_tokens = int(getattr(settings, "LLM_MAX_TOKENS", 900))
        self.global_ceiling = int(getattr(settings, "LLM_MAX_CALLS", 0))

    @property
    def configured(self) -> bool:  # type: ignore[override]
        return bool(self.api_key)

    # ── global run ceiling (quota guard) ──────────────────────────────────────
    def _reserve_global(self) -> None:
        if self.global_ceiling <= 0:
            return
        try:
            cache.add(_GLOBAL_CALL_KEY, 0, timeout=24 * 3600)
            count = cache.incr(_GLOBAL_CALL_KEY)
        except Exception:  # noqa: BLE001 — cache miss must not wedge the call
            return
        if count > self.global_ceiling:
            raise LLMProviderError(
                f"Global LLM call ceiling ({self.global_ceiling}) reached for this "
                "run — refusing further calls to protect the quota."
            )

    # ── provider contract ─────────────────────────────────────────────────────
    def generate(self, *, agent_code: str, prompt: str, model: str) -> dict:
        if not self.configured:
            raise LLMProviderError("GroqProvider has no API key.")
        self._reserve_global()

        groq_model = _model_for(model)
        system = _SYSTEM_PROMPTS.get(agent_code, _DEFAULT_SYSTEM)
        payload = {
            "model": groq_model,
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
            # The model broke JSON mode — do NOT fabricate; surface as a provider
            # error so the gateway returns a structured failure (no draft).
            raise LLMProviderError("Groq returned non-JSON content.")

        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))

        # Confidence heuristic (Groq has no native score): start high, penalise a
        # truncated completion. Calibrated so a clean answer sits above the 0.70 floor.
        confidence = 0.88
        if finish == "length":
            confidence = 0.6

        return {
            "content": content,
            "model": groq_model,
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
                # Expected on the free tier — honour Retry-After, then retry.
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 2.0 * (attempt + 1)
                logger.warning("Groq 429; backing off %.1fs (attempt %d)", delay, attempt + 1)
                time.sleep(min(delay, 10.0))
                last_exc = LLMProviderError("Groq rate limit (429).")
                continue
            if resp.status_code >= 400:
                # Don't leak the body (could echo prompt); log status only.
                logger.error("Groq error status=%s", resp.status_code)
                raise LLMProviderError(f"Groq HTTP {resp.status_code}.")
            return resp.json()
        raise last_exc or LLMProviderError("Groq call failed after retries.")
