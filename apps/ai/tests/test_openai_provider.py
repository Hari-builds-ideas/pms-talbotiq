"""
OpenAIProvider unit tests — the OpenAI Chat Completions response shape, parsed with
NO network (requests.post is mocked). The live OpenAI call is never made in the suite;
the FakeLLMProvider covers the full agent graphs elsewhere. The fake key here is
deliberately NOT an 'sk-' string (it is not, and must never resemble, a real key).
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from apps.ai.exceptions import LLMProviderError
from apps.ai.openai_provider import OpenAIProvider, _model_for

FAKE = {
    "OPENAI_API_KEY": "test-key-not-real",
    "OPENAI_BASE_URL": "https://api.openai.com/v1",
    "LLM_MAX_CALLS": 0,
    "LLM_MODEL_MAP": {"review": "gpt-4o", "chat": "gpt-4o-mini", "default": "gpt-4o-mini"},
}


def _resp(status=200, body=None, headers=None):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = body or {}
    m.headers = headers or {}
    return m


def _completion(content_obj, *, finish="stop", pt=120, ct=80):
    return {
        "choices": [{"finish_reason": finish, "message": {"content": json.dumps(content_obj)}}],
        "usage": {"prompt_tokens": pt, "completion_tokens": ct},
    }


def test_unconfigured_without_key_stays_on_503_path():
    with override_settings(OPENAI_API_KEY="", LLM_API_KEY=""):
        provider = OpenAIProvider()
        assert provider.configured is False
        with pytest.raises(LLMProviderError):
            provider.generate(agent_code="chat", prompt="hi", model="chat")


@override_settings(**FAKE)
def test_generate_parses_openai_shape_and_builds_request():
    body = _completion({"sections": {"summary": "ok", "strengths": "x", "growth": "y"}})
    with patch("apps.ai.openai_provider.requests.post", return_value=_resp(200, body)) as post:
        out = OpenAIProvider().generate(agent_code="review", prompt="draft this review", model="review")

    # Parsed result matches the gateway's expected contract.
    assert out["content"]["sections"]["summary"] == "ok"
    assert out["model"] == "gpt-4o"  # strong model for a human-read agent
    assert out["prompt_tokens"] == 120 and out["completion_tokens"] == 80
    assert out["confidence"] == 0.88

    # Request was an OpenAI Chat-Completions JSON-mode call with Bearer auth.
    url = post.call_args.args[0]
    payload = post.call_args.kwargs["json"]
    headers = post.call_args.kwargs["headers"]
    assert url == "https://api.openai.com/v1/chat/completions"
    assert payload["model"] == "gpt-4o"
    assert payload["response_format"] == {"type": "json_object"}
    assert headers["Authorization"] == "Bearer test-key-not-real"


@override_settings(**FAKE)
def test_request_uses_a_bounded_connect_and_read_timeout():
    """A slow/unreachable OpenAI must degrade quickly, never hang open-ended (the
    "Request AI Draft" spinner). The request carries a hard (connect, read) timeout
    tuple — both finite, connect capped short so an unreachable host fails fast."""
    body = _completion({"intent": "general"})
    with patch("apps.ai.openai_provider.requests.post", return_value=_resp(200, body)) as post:
        OpenAIProvider().generate(agent_code="chat", prompt="hi json", model="chat")
    timeout = post.call_args.kwargs["timeout"]
    assert isinstance(timeout, tuple) and len(timeout) == 2
    connect, read = timeout
    assert 0 < connect <= 10  # fail fast on an unreachable host
    assert 0 < read <= 60  # bounded read — never open-ended


@override_settings(**FAKE)
def test_non_json_content_raises_provider_error_not_fabrication():
    bad = {"choices": [{"finish_reason": "stop", "message": {"content": "not json at all"}}], "usage": {}}
    with patch("apps.ai.openai_provider.requests.post", return_value=_resp(200, bad)):
        with pytest.raises(LLMProviderError):
            OpenAIProvider().generate(agent_code="review", prompt="x", model="review")


@override_settings(**FAKE)
def test_truncated_completion_lowers_confidence():
    body = _completion({"sections": {}}, finish="length")
    with patch("apps.ai.openai_provider.requests.post", return_value=_resp(200, body)):
        out = OpenAIProvider().generate(agent_code="review", prompt="x", model="review")
    assert out["confidence"] == 0.6


@override_settings(**FAKE)
def test_http_error_raises_without_leaking_body():
    with patch("apps.ai.openai_provider.requests.post", return_value=_resp(400, {})):
        with pytest.raises(LLMProviderError) as exc:
            OpenAIProvider().generate(agent_code="chat", prompt="x", model="chat")
    assert "400" in str(exc.value)  # status only — no prompt/body echo


@override_settings(**FAKE, LLM_SYSTEM_PROMPTS={"chat": "Classify the intent."})  # no 'json' token
def test_json_mode_guard_injects_json_when_prompt_omits_it():
    """OpenAI's json_object mode 400s unless 'json' appears in the messages; the guard
    appends it when a (custom) system prompt omits the word."""
    body = _completion({"intent": "general"})
    with patch("apps.ai.openai_provider.requests.post", return_value=_resp(200, body)) as post:
        OpenAIProvider().generate(agent_code="chat", prompt="how are you", model="chat")
    system_msg = post.call_args.kwargs["json"]["messages"][0]["content"].lower()
    assert "json" in system_msg


@override_settings(**{**FAKE, "LLM_MAX_CALLS": 1})
def test_global_ceiling_blocks_runaway():
    with patch("apps.ai.openai_provider.atomic.incr_window", return_value=2):  # over the ceiling of 1
        with pytest.raises(LLMProviderError) as exc:
            OpenAIProvider().generate(agent_code="chat", prompt="x", model="chat")
    assert "ceiling" in str(exc.value).lower()


def test_model_map_resolves_logical_names():
    with override_settings(LLM_MODEL_MAP={"review": "gpt-4o", "default": "gpt-4o-mini"}):
        assert _model_for("review") == "gpt-4o"
        assert _model_for("unknown") == "gpt-4o-mini"  # falls back to 'default'
