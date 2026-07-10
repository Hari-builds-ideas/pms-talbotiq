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
def test_http_error_raises_without_leaking_body():
    with patch("apps.ai.gemini_provider.requests.post", return_value=_resp(400, {})):
        with pytest.raises(LLMProviderError) as exc:
            GeminiProvider().generate(agent_code="chat", prompt="x", model="chat")
    assert "400" in str(exc.value)


def test_model_resolution_prefers_gemini_names_else_default():
    # An OpenAI name in the map → replaced by the Gemini default.
    with override_settings(LLM_MODEL_MAP={"review": "gpt-4o"}, GEMINI_MODEL="gemini-1.5-flash"):
        assert _model_for("review") == "gemini-1.5-flash"
    # A Gemini name in the map → used as-is (v2 could add a per-agent Gemini map).
    with override_settings(LLM_MODEL_MAP={"review": "gemini-1.5-pro"}, GEMINI_MODEL="gemini-1.5-flash"):
        assert _model_for("review") == "gemini-1.5-pro"
