"""Tests for Sentry wiring: disabled-without-DSN boot + before_send scrubbing."""
from apps.core.observability import _BODY_DROPPED, before_send, init_sentry
from apps.core.request_context import reset_request_id, set_request_id
from apps.tenancy.context import set_current_tenant_id, reset_current_tenant_id


def test_init_sentry_disabled_without_dsn():
    """Empty DSN -> no init, returns False, must not raise (app still boots)."""
    assert init_sentry(dsn="") is False


def test_before_send_scrubs_headers_and_data():
    """Authorization header is dropped; sensitive data keys are redacted."""
    event = {
        "request": {
            "headers": {"Authorization": "Bearer secret", "Accept": "application/json"},
            "cookies": {"sessionid": "abc", "token": "leak"},
            "data": {
                "password": "hunter2",
                "access": "jwt-access",
                "refresh": "jwt-refresh",
                "token": "raw-token",
                "email": "x@y.com",
            },
        },
        "extra": {"mfa_token": "123456", "note": "keep"},
    }

    result = before_send(event, hint={})

    headers = result["request"]["headers"]
    assert "Authorization" not in headers
    assert headers["Accept"] == "application/json"  # non-sensitive preserved

    # C12 strengthened this. The body used to be key-redacted, which kept every
    # field whose name did not look sensitive — including `email` here, and
    # including `draft_body` (a written performance review) in real traffic. The
    # whole body is now dropped, so none of it can reach the error store.
    assert result["request"]["data"] == _BODY_DROPPED
    for leaked in ("hunter2", "jwt-access", "jwt-refresh", "raw-token", "x@y.com"):
        assert leaked not in str(result)

    assert result["request"]["cookies"]["token"] == "[Filtered]"
    assert result["request"]["cookies"]["sessionid"] == "abc"

    assert result["extra"]["mfa_token"] == "[Filtered]"
    assert result["extra"]["note"] == "keep"


def test_before_send_is_defensive_about_missing_structures():
    """A bare event (no request/extra) must pass through without raising."""
    assert before_send({}, hint={}) == {"tags": {}}


def test_before_send_tags_with_request_and_tenant_ids():
    """Active correlation context is mirrored into event tags."""
    req_token = set_request_id("req-123")
    tenant_token = set_current_tenant_id("tenant-9")
    try:
        result = before_send({}, hint={})
        assert result["tags"]["request_id"] == "req-123"
        assert result["tags"]["tenant_id"] == "tenant-9"
    finally:
        reset_current_tenant_id(tenant_token)
        reset_request_id(req_token)
