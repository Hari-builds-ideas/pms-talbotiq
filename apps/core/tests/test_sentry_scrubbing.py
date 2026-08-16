"""
Sentry scrubbing (C12).

This system stores written performance reviews, 360 feedback, 1:1 notes and
weekly check-ins. An unscrubbed error store is a second copy of exactly that
text — held by a third party, on a different retention policy, readable by
anyone with a Sentry login. These pin what may and may not leave the process.
"""
from apps.core.observability import _BODY_DROPPED, _REDACTED, before_send


def _event(**request):
    return {"request": request}


# ── request bodies ────────────────────────────────────────────────────────────

def test_a_review_body_never_leaves_the_process():
    """The case that motivates dropping bodies wholesale: `draft_body` is a
    written performance review, and the key name looks entirely innocuous."""
    event = _event(data={"draft_body": "Priya missed three of five goals this cycle."})
    out = before_send(event, None)
    assert "Priya" not in str(out)
    assert "missed three" not in str(out)
    assert out["request"]["data"] == _BODY_DROPPED


def test_feedback_and_checkin_text_are_dropped_too():
    for payload in (
        {"body": "He talks over people in standup."},
        {"blockers": "I'm being managed out and nobody will say it."},
        {"comment": "Not ready for promotion, keep it off the record."},
    ):
        out = before_send(_event(data=payload), None)
        assert out["request"]["data"] == _BODY_DROPPED, payload


def test_the_marker_says_a_body_existed():
    """Silently removing the key would leave a developer unsure whether the
    request was empty or scrubbed."""
    out = before_send(_event(data={"anything": 1}), None)
    assert "dropped" in out["request"]["data"]


def test_an_empty_body_is_removed_rather_than_marked():
    for empty in (None, "", {}, []):
        out = before_send(_event(data=empty), None)
        assert "data" not in out["request"]


def test_a_body_that_is_a_bare_string_is_still_dropped():
    # Sentry payload shapes vary by integration; a non-dict body must not slip past.
    out = before_send(_event(data="raw=Priya+is+underperforming"), None)
    assert out["request"]["data"] == _BODY_DROPPED


# ── headers, cookies, query string ────────────────────────────────────────────

def test_authorization_and_cookie_headers_are_removed():
    out = before_send(
        _event(headers={"Authorization": "Bearer abc.def", "Cookie": "sid=1",
                        "User-Agent": "curl/8"}),
        None,
    )
    headers = out["request"]["headers"]
    assert "Authorization" not in headers and "Cookie" not in headers
    # Non-sensitive headers survive — they are useful and harmless.
    assert headers["User-Agent"] == "curl/8"


def test_session_cookies_are_redacted():
    out = before_send(_event(cookies={"access": "a.b.c", "theme": "dark"}), None)
    assert out["request"]["cookies"]["access"] == _REDACTED
    assert out["request"]["cookies"]["theme"] == "dark"


def test_a_token_in_the_query_string_is_redacted():
    """Invitation and password-reset links carry one, so a GET that 500s would
    otherwise ship a working credential to the error store."""
    out = before_send(_event(query_string="token=live-single-use-value&page=2"), None)
    qs = out["request"]["query_string"]
    assert "live-single-use-value" not in qs
    assert _REDACTED in qs
    assert "page=2" in qs  # ordinary params survive


def test_extra_context_is_scrubbed():
    event = {"extra": {"password": "hunter2", "tenant_slug": "acme"}}
    out = before_send(event, None)
    assert out["extra"]["password"] == _REDACTED
    assert out["extra"]["tenant_slug"] == "acme"


# ── what must SURVIVE ─────────────────────────────────────────────────────────

def test_what_is_needed_to_debug_still_survives():
    """Scrubbing that removes the ability to debug gets turned off. The stack
    trace, endpoint, tenant and request id all remain."""
    event = {
        "request": {"url": "/api/reviews/abc/submit", "method": "POST",
                    "data": {"draft_body": "secret"}},
        "exception": {"values": [{"type": "ValueError", "value": "boom"}]},
    }
    out = before_send(event, None)
    assert out["request"]["url"] == "/api/reviews/abc/submit"
    assert out["request"]["method"] == "POST"
    assert out["exception"]["values"][0]["type"] == "ValueError"


def test_malformed_payloads_do_not_raise():
    """before_send runs inside the SDK's error path. Raising there loses the
    event AND masks the original error."""
    for event in ({}, {"request": None}, {"request": "nope"}, {"extra": []}):
        assert before_send(dict(event), None) is not None
