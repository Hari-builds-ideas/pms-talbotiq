"""
Sentry wiring — initialization and PII/secret scrubbing.

``init_sentry`` is a no-op when no DSN is configured, so the app boots normally
in environments where Sentry is disabled (local dev, CI). When enabled it wires
the Django and Celery integrations and routes every event through
``before_send``, which scrubs credentials before anything leaves the process
and tags events with the current tenant + request id for correlation.

``send_default_pii=False`` is set as defence-in-depth; ``before_send`` is the
authoritative scrubber and is kept import-light so it never depends on
``sentry_sdk`` being importable.
"""

# Keys whose values must never leave the process, matched case-insensitively
# wherever they appear in request data / cookies / extra.
_SENSITIVE_KEYS = frozenset(
    {
        "authorization", "token", "access", "refresh", "password", "mfa_token",
        # Anything that is itself a credential or a way to get one.
        "api_key", "apikey", "secret", "client_secret", "signature", "code",
        "new_password", "current_password", "email_change_token",
    }
)
_REDACTED = "[Filtered]"
#: Stands in for a dropped request body, so a reader knows one existed rather
#: than wondering whether the request was empty.
_BODY_DROPPED = "[request body dropped — may contain employee performance data]"


def _scrub_headers(headers):
    """Drop Authorization/Cookie headers (case-insensitive key match)."""
    if not isinstance(headers, dict):
        return
    for key in list(headers.keys()):
        if isinstance(key, str) and key.lower() in {"authorization", "cookie"}:
            headers.pop(key, None)


def _scrub_mapping(mapping):
    """Redact any sensitive-named keys in a mapping (case-insensitive)."""
    if not isinstance(mapping, dict):
        return
    for key in list(mapping.keys()):
        if isinstance(key, str) and key.lower() in _SENSITIVE_KEYS:
            mapping[key] = _REDACTED


def _drop_body(request):
    """Remove the request body entirely (C12).

    Key-based redaction was not enough here, and the reason is what this product
    stores. A POST to /api/reviews/<id>/submit carries ``draft_body`` — a written
    performance review. /api/feedback/continuous carries somebody's 360 feedback.
    /api/checkins carries what a person said was blocking them this week. None of
    those key names look sensitive, so a denylist keeps every one of them, and the
    error store quietly becomes a second copy of the most sensitive text in the
    system — held by a third party, on a different retention policy, readable by
    anyone with a Sentry login.

    Enumerating the fields that DO matter is the wrong shape of defence: the list
    is long, it grows with every feature, and forgetting one entry is silent. So
    the body goes, wholesale. A marker is left behind so a developer reading the
    event knows a body existed and is not left wondering whether the request was
    empty.

    What is lost is real — payload shape is genuinely useful when debugging a 500
    — but the stack trace, the endpoint, the tenant and the request id all survive,
    and those answer most of it. Employee performance text leaving the system is
    not a debugging convenience worth paying for.
    """
    if not isinstance(request, dict) or "data" not in request:
        return
    data = request.get("data")
    if data in (None, "", {}, []):
        request.pop("data", None)
        return
    request["data"] = _BODY_DROPPED


def _scrub_query_string(request):
    """Redact sensitive-looking query parameters.

    Tokens do end up in query strings — the invitation and password-reset links
    both carry one — and a GET that 500s would otherwise ship a working
    credential to the error store.
    """
    qs = request.get("query_string")
    if not isinstance(qs, str) or not qs:
        return
    parts = []
    for pair in qs.split("&"):
        key, sep, _value = pair.partition("=")
        if sep and key.lower() in _SENSITIVE_KEYS:
            parts.append(f"{key}={_REDACTED}")
        else:
            parts.append(pair)
    request["query_string"] = "&".join(parts)


def before_send(event, hint):
    """Scrub secrets and tag with correlation ids before an event is sent.

    Defensive throughout: every nested structure may be missing or not a dict
    (Sentry payloads vary by integration), so we type-check before touching it.
    """
    request = event.get("request")
    if isinstance(request, dict):
        _scrub_headers(request.get("headers"))
        _drop_body(request)
        _scrub_mapping(request.get("cookies"))
        _scrub_query_string(request)

    _scrub_mapping(event.get("extra"))

    # Tag with tenant + request id for correlation, only when present.
    from apps.tenancy.context import get_current_tenant_id

    from .request_context import get_request_id

    tags = event.setdefault("tags", {})
    tenant_id = get_current_tenant_id()
    if tenant_id is not None:
        tags["tenant_id"] = tenant_id
    request_id = get_request_id()
    if request_id is not None:
        tags["request_id"] = request_id

    return event


def init_sentry(*, dsn, environment="dev", traces_sample_rate=0.0):
    """Initialize Sentry. Returns False (no-op) when ``dsn`` is falsy.

    Imports ``sentry_sdk`` and its integrations lazily so this module imports
    even if the SDK were absent, and so disabling Sentry has zero import cost.
    """
    if not dsn:
        return False

    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        traces_sample_rate=traces_sample_rate,
        send_default_pii=False,
        before_send=before_send,
        integrations=[DjangoIntegration(), CeleryIntegration()],
    )
    return True
