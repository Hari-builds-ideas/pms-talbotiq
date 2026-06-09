"""
Current-request-id context.

The correlation id for a unit of work is held in a contextvar (thread- and
async-safe). It is set ONLY by ``RequestIDMiddleware`` on the request path —
either echoing an inbound ``X-Request-ID`` header or minting a fresh uuid — and
read by the logging filter / observability layer so every log line and Sentry
event can be tied back to a single HTTP request.

Mirrors ``apps.tenancy.context``: a single ContextVar with get/set/reset
helpers and the same no-bleed reset discipline driven from the middleware's
``finally``.
"""
import contextvars

_current_request_id: contextvars.ContextVar = contextvars.ContextVar(
    "pms_current_request_id", default=None
)


def get_request_id():
    """Return the active request id (str) or None when none is bound."""
    return _current_request_id.get()


def set_request_id(value):
    """Bind the current request id; returns a token for ``reset_request_id``."""
    return _current_request_id.set(value)


def reset_request_id(token):
    """Reset the request id to its previous value using ``token``."""
    _current_request_id.reset(token)
