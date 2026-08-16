"""
TenantMiddleware — resolves the current tenant from the verified JWT.

It reads ``tenant_id`` and ``role`` ONLY from the cryptographically verified
JWT access-token claims (signature + expiry checked by simplejwt) — never from
headers, query string, or body, which are spoofable. The resolved tenant is
bound into the contextvar for the duration of the request and reset afterwards
so nothing leaks between requests served on the same worker thread.
"""
import logging

from django.http import JsonResponse
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from .context import (
    mark_request_active,
    reset_current_tenant_id,
    reset_request_active,
    set_current_tenant_id,
)
from .status import tenant_is_active

logger = logging.getLogger("pms.tenancy")


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._jwt = JWTAuthentication()

    def __call__(self, request):
        tenant_token = None
        request_token = mark_request_active()
        try:
            tenant_id, role = self._resolve_from_jwt(request)
            request.tenant_id = tenant_id
            request.tenant_role = role
            if tenant_id is not None:
                # A SUSPENDED or CANCELLED tenant is refused here, not only at
                # login (C3). Checking it only at login meant suspending a tenant
                # did nothing to anyone already signed in: their access token kept
                # working for its full 15 minutes and their refresh token kept
                # rotating for up to 7 days. For suspend-for-non-payment or
                # suspend-for-breach, that window is the whole point.
                #
                # The status is cached and invalidated by a post_save signal, so
                # this costs a cache read rather than a query per request.
                if not tenant_is_active(tenant_id):
                    return self._suspended_response(tenant_id)
                tenant_token = set_current_tenant_id(tenant_id)
            return self.get_response(request)
        finally:
            if tenant_token is not None:
                reset_current_tenant_id(tenant_token)
            reset_request_active(request_token)

    @staticmethod
    def _suspended_response(tenant_id):
        """401 with a code the client can act on.

        401 rather than 403: the credential is no longer good for anything, and
        the SPA's axios interceptor already treats 401 as "this session is over"
        — it clears tokens and returns to login, which is exactly the behaviour
        wanted. A 403 would leave the user staring at a broken page still holding
        a token that will never work again.

        The message says the organisation, not the person: an employee of a
        suspended tenant has done nothing wrong and should be told who to ask.
        """
        logger.info("Refused a request for non-active tenant=%s", tenant_id)
        return JsonResponse(
            {
                "detail": (
                    "This workspace is not active. Please contact your "
                    "administrator or our support team."
                ),
                "code": "tenant_inactive",
            },
            status=401,
        )

    def _resolve_from_jwt(self, request):
        header = self._jwt.get_header(request)
        if header is None:
            return None, None
        raw_token = self._jwt.get_raw_token(header)
        if raw_token is None:
            return None, None
        try:
            validated = self._jwt.get_validated_token(raw_token)
        except (InvalidToken, TokenError):
            # Invalid/expired token: leave tenant unbound. DRF auth on the view
            # will reject protected endpoints with 401; public endpoints proceed.
            return None, None
        tenant_id = validated.get("tenant_id")
        role = validated.get("role")
        return (str(tenant_id) if tenant_id is not None else None), role
