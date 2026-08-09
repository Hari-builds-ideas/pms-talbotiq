"""
GeminiProvider unit tests — Gemini's OpenAI-compatible Chat Completions shape, parsed
with NO network (requests.post mocked). Mirrors test_openai_provider.py. The fake key is
deliberately not a real-looking key.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from apps.ai.exceptions import LLMProviderError
from apps.ai.gemini_provider import GeminiProvider, _model_for

FAKE = {
    "GEMINI_API_KEY": "test-gemini-key-not-real",
    "GEMINI_MODEL": "gemini-1.5-flash",
    "LLM_MAX_CALLS": 0,
    # The map holds OpenAI names — the Gemini provider must NOT send those to Gemini.
    "LLM_MODEL_MAP": {"review": "gpt-4o", "chat": "gpt-4o-mini", "default": "gpt-4o-mini"},
}


def _resp(status=200, body=None, headers=None):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = body or {}
    m.headers = headers or {}
    return m


def _completion(content_obj, *, finish="stop", pt=100, ct=60):
    return {
        "choices": [{"finish_reason": finish, "message": {"content": json.dumps(content_obj)}}],
        "usage": {"prompt_tokens": pt, "completion_tokens": ct},
    }


def test_unconfigured_without_key_stays_on_503_path():
    with override_settings(GEMINI_API_KEY="", LLM_API_KEY=""):
        provider = GeminiProvider()
        assert provider.configured is False
        with pytest.raises(LLMProviderError):
            provider.generate(agent_code="chat", prompt="hi", model="chat")


@override_settings(**FAKE)
def test_generate_hits_gemini_openai_endpoint_with_a_gemini_model():
    body = _completion({"sections": {"summary": "ok"}})
    with patch("apps.ai.gemini_provider.requests.post", return_value=_resp(200, body)) as post:
        out = GeminiProvider().generate(agent_code="review", prompt="draft this review", model="review")

    assert out["content"]["sections"]["summary"] == "ok"
    # The OpenAI model name in the map must be swapped for a Gemini model.
    assert out["model"] == "gemini-1.5-flash"
    assert out["confidence"] == 0.88
    url = post.call_args.args[0]
    payload = post.call_args.kwargs["json"]
    headers = post.call_args.kwargs["headers"]
    assert url == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert payload["model"] == "gemini-1.5-flash"
    assert headers["Authorization"] == "Bearer test-gemini-key-not-real"


@override_settings(**FAKE)
def test_non_json_content_raises_provider_error_not_fabrication():
    bad = {"choices": [{"finish_reason": "stop", "message": {"content": "not json"}}], "usage": {}}
    with patch("apps.ai.gemini_provider.requests.post", return_value=_resp(200, bad)):
        with pytest.raises(LLMProviderError):
            GeminiProvider().generate(agent_code="review", prompt="x", model="review")


@override_settings(**FAKE)
def test_a_truncated_completion_blames_the_token_ceiling_not_the_model():
    """Agent-1 failed 100% of the time in the demo deploy, reporting "returned non-JSON
    content" — which points at the prompt. The real cause was our own max_tokens pin
    cutting the JSON off mid-string. The two need opposite fixes, so the message has to
    tell them apart."""
    cut = {"choices": [{"finish_reason": "length",
                        "message": {"content": '{"draft_body": "It was the best of ti'}}],
           "usage": {}}
    with patch("apps.ai.gemini_provider.requests.post", return_value=_resp(200, cut)):
        with pytest.raises(LLMProviderError) as exc:
            GeminiProvider().generate(agent_code="review", prompt="x", model="review")
    assert "cut off" in str(exc.value) and "LLM_MAX_TOKENS" in str(exc.value)
    assert "non-JSON" not in str(exc.value)


@override_settings(**FAKE)
def test_http_error_raises_without_leaking_body():
    with patch("apps.ai.gemini_provider.requests.post", return_value=_resp(400, {})):
        with pytest.raises(LLMProviderError) as exc:
            GeminiProvider().generate(agent_code="chat", prompt="x", model="chat")
    assert "400" in str(exc.value)


def test_model_resolution_best_fast_split_and_ignores_non_gemini():
    base = {"GEMINI_MODEL": "", "GEMINI_MODEL_BEST": "gemini-2.5-pro", "GEMINI_MODEL_FAST": "gemini-2.5-flash"}
    # No overrides → human-read agents get BEST, chat/default get FAST.
    with override_settings(GEMINI_MODEL_MAP={}, **base):
        assert _model_for("review") == "gemini-2.5-pro"
        assert _model_for("feedback") == "gemini-2.5-pro"
        assert _model_for("chat") == "gemini-2.5-flash"
        assert _model_for("default") == "gemini-2.5-flash"
    # A Gemini name in the per-agent map is used as-is.
    with override_settings(GEMINI_MODEL_MAP={"review": "gemini-1.5-pro"}, **base):
        assert _model_for("review") == "gemini-1.5-pro"
    # A stray OpenAI name (leaked via a shared LLM_MODEL_* override) is IGNORED → the
    # Gemini default, so an OpenAI id never reaches Gemini.
    with override_settings(GEMINI_MODEL_MAP={"review": "gpt-4o"}, **base):
        assert _model_for("review") == "gemini-2.5-pro"
    # A single GEMINI_MODEL override forces one model for EVERY agent.
    with override_settings(GEMINI_MODEL="gemini-1.5-flash", GEMINI_MODEL_MAP={"review": "gemini-2.5-pro"}):
        assert _model_for("review") == "gemini-1.5-flash"
        assert _model_for("chat") == "gemini-1.5-flash"
