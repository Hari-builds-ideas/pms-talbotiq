"""
The Google Gemini LLM provider — a sibling of :mod:`apps.ai.openai_provider`.

Gemini ships an **OpenAI-compatible** Chat Completions endpoint
(``https://generativelanguage.googleapis.com/v1beta/openai``), so the gateway pipeline
(budget → PII-scrub → call → schema-validate → meter → confidence → PENDING) is byte-for-byte
unchanged from the OpenAI path — only the base URL, the key (``GEMINI_API_KEY``), and the model
names differ. This is the free-tier provider for the demo deploy (V1_C): Gemini's free tier
serves the AI on the key Hari pastes into the Render dashboard.

Model resolution (two-model strategy, mirroring the OpenAI provider): the human-read agents
(review / feedback / succession / JD / career) get Gemini's **best** model
(``settings.GEMINI_MODEL_BEST``, default ``gemini-pro-latest``) and chat/default get a **fast** model
(``settings.GEMINI_MODEL_FAST``, default ``gemini-2.5-flash``) — both env-overridable. A single
``GEMINI_MODEL`` env var still forces one model for every agent if set. The generic
``LLM_MODEL_MAP`` holds OpenAI names, which Gemini rejects, so this provider NEVER reads it — it
uses ``GEMINI_MODEL_MAP`` and ignores any value that isn't a Gemini model.

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
#: Best / fast defaults if settings are somehow unset. (`gemini-2.5-pro` is blocked for
#: new API projects, so the best default is the stable `gemini-pro-latest` alias.)
_DEFAULT_BEST = "gemini-pro-latest"
_DEFAULT_FAST = "gemini-2.5-flash"
#: The human-read agents that get the BEST model (quality where it's read by a person).
_HUMAN_READ = frozenset({"review", "feedback", "succession", "jd", "career"})


def _model_for(logical: str) -> str:
    """Resolve a logical agent name (e.g. 'review', 'chat') to a Gemini model id.

    Precedence: a single ``GEMINI_MODEL`` override (if it names a Gemini model) →
    the per-agent ``GEMINI_MODEL_MAP`` value (if it names a Gemini model) → the
    best/fast split (best for human-read agents, fast otherwise). Any non-Gemini name
    (an OpenAI/Groq id leaked via a shared ``LLM_MODEL_*`` override) is ignored so it
    never reaches Gemini.
    """
    forced = getattr(settings, "GEMINI_MODEL", "") or ""
    if forced.startswith("gemini"):
        return forced
    mapped = (getattr(settings, "GEMINI_MODEL_MAP", {}) or {}).get(logical) or ""
    if mapped.startswith("gemini"):
        return mapped
    best = getattr(settings, "GEMINI_MODEL_BEST", "") or _DEFAULT_BEST
    fast = getattr(settings, "GEMINI_MODEL_FAST", "") or _DEFAULT_FAST
    return best if logical in _HUMAN_READ else fast


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
        # A larger READ budget for a slow "thinking" model (the connect timeout
        # stays short). Kept under the AI-job soft limit so the Celery backstop wins.
        self.read_timeout = float(getattr(settings, "LLM_READ_TIMEOUT", 60))
        self.max_tokens = int(getattr(settings, "LLM_MAX_TOKENS", 900))
        self.global_ceiling = int(getattr(settings, "LLM_MAX_CALLS", 0))

    @property
    def configured(self) -> bool:  # type: ignore[override]
        return bool(self.api_key)

    # ── global run ceiling (quota guard — matters on any metered tier) ──────────
    def _reserve_global(self) -> None:
        if self.global_ceiling <= 0:
            return
        window_s = int(getattr(settings, "LLM_CALL_WINDOW_SECONDS", 3600))
        try:
            count = atomic.incr_window(_GLOBAL_CALL_KEY, ttl_ms=window_s * 1000)
        except Exception:  # noqa: BLE001 — a cache miss must not wedge the call
            return
        if count > self.global_ceiling:
            mins = max(1, window_s // 60)
            raise LLMGlobalCeilingError(
                f"Global LLM call ceiling ({self.global_ceiling}) reached — pausing "
                f"further calls to protect the quota. It resets within {mins} minute(s)."
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
            # Blame the right thing. A completion we cut off at max_tokens is
            # unterminated JSON, and reporting that as "the model broke JSON mode"
            # sends the reader to the prompt when the fix is the budget. Agent-1
            # failed 100% of the time behind this message for exactly that reason.
            if finish == "length":
                raise LLMProviderError(
                    f"Gemini response was cut off at the {self.max_tokens}-token ceiling, "
                    "so the JSON is unterminated — raise LLM_MAX_TOKENS."
                )
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

    # ── function-calling (AGENT_V3/B) ─────────────────────────────────────────
    def generate_with_tools(self, *, agent_code: str, messages: list, tools: list,
                            model: str) -> dict:
        """One turn of a tool-calling conversation.

        Returns either an assistant message carrying ``tool_calls`` (the model wants
        data) or one carrying ``content`` (the final answer). The caller runs the tools
        and calls back in with the results appended — this method holds no state, so a
        retry or a crash can never leave half a conversation behind.

        Deliberately NOT JSON mode: the final answer is prose for a person to read, and
        the structure we care about arrives as ``tool_calls``, which the endpoint returns
        as typed fields rather than as text we would have to parse back.
        """
        if not self.configured:
            raise LLMProviderError("GeminiProvider has no API key.")
        self._reserve_global()

        payload = {
            "model": _model_for(model),
            "messages": messages,
            "temperature": 0.1,  # lower than prose: tool ARGUMENTS should not be creative
            "max_tokens": self.max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        data = self._post_with_backoff(f"{self.base_url}/chat/completions", payload, headers)
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        return {
            "content": message.get("content") or "",
            "tool_calls": message.get("tool_calls") or [],
            "finish_reason": choice.get("finish_reason"),
            "model": payload["model"],
            "prompt_tokens": int(usage.get("prompt_tokens", 0)),
            "completion_tokens": int(usage.get("completion_tokens", 0)),
        }

    def _post_with_backoff(self, url, payload, headers, *, attempts=3) -> dict:
        """POST with retry+backoff on the TRANSIENT failures — connection errors,
        429 (honoring Retry-After), and 5xx — with jitter so many concurrent jobs
        don't retry in lockstep (thundering herd). A 4xx other than 429 is a client
        error that won't fix on retry, so it fails fast. After the cap, raise
        ``LLMProviderError`` → the gateway records PROVIDER_ERROR and the job
        degrades gracefully (never fabricates)."""
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                resp = requests.post(
                    url, json=payload, headers=headers,
                    timeout=(min(self.timeout, 10.0), self.read_timeout),
                )
            except requests.RequestException as exc:
                last_exc = exc
                self._sleep(1.5 * (attempt + 1))
                continue
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 2.0 * (attempt + 1)
                logger.warning("Gemini 429; backing off %.1fs (attempt %d)", delay, attempt + 1)
                self._sleep(min(delay, 10.0))
                last_exc = LLMProviderError("Gemini rate limit (429).")
                continue
            if 500 <= resp.status_code < 600:
                # Transient server error — retry with backoff instead of failing the
                # whole job on the first blip.
                logger.warning("Gemini %s; backing off (attempt %d)", resp.status_code, attempt + 1)
                self._sleep(2.0 * (attempt + 1))
                last_exc = LLMProviderError(f"Gemini HTTP {resp.status_code}.")
                continue
            if resp.status_code >= 400:
                # 4xx (non-429): a client error (bad model id, bad key) — won't fix on
                # retry. Don't leak the body (could echo the prompt); log status only.
                logger.error("Gemini error status=%s", resp.status_code)
                raise LLMProviderError(f"Gemini HTTP {resp.status_code}.")
            return resp.json()
        raise last_exc or LLMProviderError("Gemini call failed after retries.")

    @staticmethod
    def _sleep(base: float) -> None:
        """Sleep ``base`` seconds plus a little random jitter (de-synchronises the
        retries of many concurrent jobs). Capped so a retry can't blow the job budget."""
        import random

        time.sleep(min(base + random.uniform(0, 0.75), 10.0))
