"""
Entitlement-driven request throttling.

Three throttles share one mechanism: each resolves its rate per request from the
caller's tenant entitlement (via :func:`apps.billing.services.rate_limits_for`),
so an upgrade to FULL_AI lifts the limits everywhere at once without touching any
view. The scopes are:

* :class:`TenantThrottle` — a single bucket per tenant (all of a tenant's users
  share it), the coarse fairness limit. Carries an upgrade hint on 429.
* :class:`UserThrottle`   — a per-user bucket, isolating one noisy user from the
  rest of their tenant. No upgrade hint (it's a personal, not commercial, limit).
* :class:`AIThrottle`     — a per-user bucket reserved for AI endpoints (wired in
  Module 10; unit-tested here). Carries an upgrade hint on 429.

SECURITY: every cache key embeds the tenant id, so one tenant's counter can never
collide with another's — counter isolation is a tenant-isolation control, exactly
like :mod:`apps.core.cache`. Anonymous / unauthenticated requests are NOT
throttled by these classes (they fall through to ``AnonRateThrottle`` on the
login surface, which is IP-based).
"""
from __future__ import annotations

import math

from rest_framework.exceptions import APIException, Throttled
from rest_framework.throttling import SimpleRateThrottle

from apps.billing.services import rate_limits_for


class RateLimited(Throttled):
    """A 429 with our own body shape and an optional upgrade hint.

    We bypass ``Throttled.__init__`` deliberately: it string-joins the supplied
    detail with a "expected available in N seconds" message, which corrupts a
    dict detail. Instead we build the dict ourselves and hand it straight to
    ``APIException.__init__``, while still setting ``self.wait`` so DRF's
    exception handler emits the ``Retry-After`` header.
    """

    def __init__(self, wait=None, scope=None, upgrade=False):
        self.wait = math.ceil(wait) if wait is not None else None
        detail = {"detail": f"Rate limit exceeded for the {scope} bucket.", "scope": scope}
        if upgrade:
            detail["upgrade_hint"] = (
                "Your plan's rate limit was reached. "
                "Upgrade to Full AI for higher limits."
            )
        APIException.__init__(self, detail)  # NOT Throttled.__init__


class _EntitlementThrottle(SimpleRateThrottle):
    """Base for the entitlement-derived throttles.

    Subclasses set :attr:`rate_key` (which slot of ``rate_limits_for`` to use),
    :attr:`include_upgrade_hint`, and :meth:`get_cache_key` (a tenant-scoped key).
    The rate is resolved per request in :meth:`allow_request`, not statically, so
    a tenant's entitlement change takes effect on its very next request.
    """

    #: Which key of the ``rate_limits_for`` map to read: "tenant" | "user" | "ai".
    rate_key = None
    #: Whether a 429 from this throttle includes the commercial upgrade hint.
    include_upgrade_hint = False

    # NOTE: DRF SimpleRateThrottle is a rolling-log window (it stores request
    # timestamps in the cache). Fixed-window is acceptable for MVP; the
    # precise-sliding-window upgrade path is a Redis sorted-set + Lua INCR/EXPIRE
    # script (see BUILD_NOTES) — swap the storage here when that lands.

    def get_rate(self):
        # Resolved dynamically per request in allow_request, not from settings.
        return None

    def allow_request(self, request, view):
        """Resolve the entitlement-derived rate for this request, then defer to
        DRF's rolling-window check. Anonymous callers are never throttled here."""
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return True  # anon falls through to AnonRateThrottle on the login surface
        tenant_id = getattr(user, "tenant_id", None)
        if not tenant_id:
            return True
        self._tenant_id = str(tenant_id)
        self._user_id = str(user.pk)
        self.rate = rate_limits_for(self._tenant_id)[self.rate_key]
        self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)

    def throttle_failure(self):
        """Raise our own 429 instead of returning ``False`` so we control the body
        and the ``Retry-After`` header (DRF turns ``self.wait`` into that header)."""
        raise RateLimited(
            wait=self.wait(),
            scope=self.rate_key,
            upgrade=self.include_upgrade_hint,
        )


class TenantThrottle(_EntitlementThrottle):
    """One shared bucket per tenant. Coarse fairness limit; hints at upgrade."""

    rate_key = "tenant"
    include_upgrade_hint = True

    def get_cache_key(self, request, view):
        return f"thr:t:{self._tenant_id}"


class UserThrottle(_EntitlementThrottle):
    """Per-user bucket within a tenant. No upgrade hint (a personal limit)."""

    rate_key = "user"

    def get_cache_key(self, request, view):
        return f"thr:u:{self._tenant_id}:{self._user_id}"


class AIThrottle(_EntitlementThrottle):
    """Per-user bucket for AI endpoints (attached per-view in Module 10)."""

    rate_key = "ai"
    include_upgrade_hint = True

    def get_cache_key(self, request, view):
        return f"thr:ai:{self._tenant_id}:{self._user_id}"
