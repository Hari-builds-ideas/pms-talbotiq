"""Tests for RequestIDMiddleware + the request-id contextvar.

``/healthz`` is dependency-free and needs no auth, so it exercises the
middleware in isolation: the middleware runs on every request regardless of the
view.
"""
from apps.core.request_context import get_request_id


def test_generates_request_id_when_none_supplied(client):
    """No inbound X-Request-ID -> a generated one is echoed on the response."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID")  # present and non-empty


def test_inbound_request_id_is_preserved(client):
    """An inbound X-Request-ID is echoed back unchanged for cross-hop tracing."""
    resp = client.get("/healthz", HTTP_X_REQUEST_ID="my-correlation-123")
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == "my-correlation-123"


def test_no_bleed_outside_request(client):
    """The contextvar is reset in finally, so nothing leaks after the request."""
    client.get("/healthz")
    assert get_request_id() is None


def test_two_requests_get_distinct_generated_ids(client):
    """Each request without an inbound id mints its own correlation id."""
    first = client.get("/healthz").headers.get("X-Request-ID")
    second = client.get("/healthz").headers.get("X-Request-ID")
    assert first and second
    assert first != second
