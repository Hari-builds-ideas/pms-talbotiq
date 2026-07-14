"""
PROD_D — AI robustness under load. Proofs for the Gemini transport hardening:
transient 5xx and 429 are retried with backoff (not failed on the first blip); a
4xx client error fails fast; after the retry cap it raises LLMProviderError so the
gateway records PROVIDER_ERROR and the job degrades gracefully (never fabricates).
``time.sleep`` is patched out so the backoff is instant in tests.
"""
import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.test import override_settings

from apps.ai.exceptions import LLMProviderError
from apps.ai.gemini_provider import GeminiProvider

FAKE = {
    "GEMINI_API_KEY": "test-gemini-key-not-real",
    "GEMINI_MODEL": "gemini-1.5-flash",
    "LLM_MAX_CALLS": 0,
}


def _resp(status=200, body=None, headers=None):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = body or {}
    m.headers = headers or {}
    return m


def _ok_body():
    return {
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"text": "ok"})}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


@contextmanager
def _mocked_post(side_effect):
    """Patch requests.post (+ sleep) for the duration of the block — kept OPEN so
    the call under test runs while the mock is active."""
    with patch("apps.ai.gemini_provider.time.sleep"), \
         patch("apps.ai.gemini_provider.requests.post", side_effect=side_effect) as post:
        yield post


@override_settings(**FAKE)
def test_retries_transient_5xx_then_succeeds():
    with _mocked_post([_resp(503), _resp(502), _resp(200, _ok_body())]) as post:
        out = GeminiProvider().generate(agent_code="chat", prompt="hi", model="chat")
    assert out["content"] == {"text": "ok"}
    assert post.call_count == 3  # two retries, then success


@override_settings(**FAKE)
def test_retries_429_honoring_retry_after_then_succeeds():
    with _mocked_post([_resp(429, headers={"Retry-After": "1"}), _resp(200, _ok_body())]) as post:
        out = GeminiProvider().generate(agent_code="chat", prompt="hi", model="chat")
    assert out["content"] == {"text": "ok"}
    assert post.call_count == 2


@override_settings(**FAKE)
def test_gives_up_after_5xx_cap_and_raises_provider_error():
    with _mocked_post([_resp(503), _resp(503), _resp(503)]) as post:
        with pytest.raises(LLMProviderError):
            GeminiProvider().generate(agent_code="chat", prompt="hi", model="chat")
    assert post.call_count == 3  # capped at 3 attempts


@override_settings(**FAKE)
def test_4xx_client_error_fails_fast_without_retry():
    # A 400 (e.g. bad model id / bad key) won't fix on retry → one call, then raise.
    with _mocked_post([_resp(400), _resp(200, _ok_body())]) as post:
        with pytest.raises(LLMProviderError):
            GeminiProvider().generate(agent_code="chat", prompt="hi", model="chat")
    assert post.call_count == 1


@override_settings(**FAKE)
def test_connection_errors_are_retried():
    with _mocked_post([requests.ConnectionError("boom"), _resp(200, _ok_body())]) as post:
        out = GeminiProvider().generate(agent_code="chat", prompt="hi", model="chat")
    assert out["content"] == {"text": "ok"}
    assert post.call_count == 2


@override_settings(**FAKE, LLM_READ_TIMEOUT=45.0)
def test_read_timeout_is_configurable_and_separate_from_connect():
    with _mocked_post([_resp(200, _ok_body())]) as post:
        GeminiProvider().generate(agent_code="chat", prompt="hi", model="chat")
    _, kwargs = post.call_args
    connect, read = kwargs["timeout"]
    assert read == 45.0 and connect <= 10.0
