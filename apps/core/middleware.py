"""
RequestIDMiddleware — request correlation id.

Each request gets a stable correlation id. If the caller (a gateway, the
frontend, or an upstream service) sends an ``X-Request-ID`` header we honour it
so logs can be traced across hops; otherwise we mint a fresh uuid. The id is
bound into a contextvar for the duration of the request (so the logging filter
and Sentry can pick it up), stashed on ``request.request_id`` for convenience,
and echoed back on the response. The contextvar is reset in a ``finally`` —
same no-bleed discipline as ``TenantMiddleware`` — so nothing leaks between
requests served on the same reused worker thread.
"""
import uuid

from .request_context import reset_request_id, set_request_id

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        inbound = request.META.get("HTTP_X_REQUEST_ID")
        request_id = inbound.strip() if inbound and inbound.strip() else uuid.uuid4().hex

        request.request_id = request_id
        token = set_request_id(request_id)
        try:
            response = self.get_response(request)
            response[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            reset_request_id(token)


class MetricsMiddleware:
    """Record each request into the cross-worker request counter (BUILD_4 4.2).
    Best-effort and AFTER the response, so it never affects latency or outcome."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            from apps.core.metrics import record_request

            record_request(request.path, response.status_code)
        except Exception:  # noqa: BLE001 — metrics must never break a response
            pass
        return response
