"""
Is a tenant still allowed to be served? (C3)

``Tenant.status`` was checked at login, SSO and password reset — and nowhere
else. Suspending a tenant therefore did nothing to anyone already signed in: an
access token kept working for its full lifetime (15 minutes) and the refresh
token kept rotating for up to 7 days. For a suspend-for-non-payment or
suspend-for-breach action, that is the window that matters.

The check now runs on every authenticated request, which means it has to be
cheap. The status is cached per tenant and invalidated by a ``post_save`` signal
on ``Tenant``, so the common path costs one cache read and no query.

**Fails closed.** If the tenant cannot be read at all, the request is refused.
This is the "is this customer allowed to use the product" question; answering
"probably, carry on" when we do not know is the wrong way round.
"""
from __future__ import annotations

import logging

from django.core.cache import caches

logger = logging.getLogger("pms.tenancy.status")

#: Deliberately NOT built with tenant_cache_key: that namespace is cleared
#: wholesale by invalidate_tenant_cache() during ordinary data churn, and losing
#: this key on every entitlement edit would put a query back on every request.
_KEY = "tenancy:status:{}"

#: A backstop, not the mechanism. The signal below is what makes a suspension
#: take effect immediately; this only bounds how long a stale value could survive
#: if a write happened somewhere the signal did not fire (a raw SQL update, a
#: fixture load, another process).
_TTL_SECONDS = 300


def tenant_status(tenant_id) -> str | None:
    """The tenant's status string, cached. None when it cannot be determined."""
    if tenant_id is None:
        return None
    key = _KEY.format(tenant_id)
    cache = caches["default"]
    try:
        cached = cache.get(key)
    except Exception:  # noqa: BLE001 — a cache outage must not break auth
        cached = None
    if cached is not None:
        return cached or None

    from .models import Tenant

    try:
        status = (
            Tenant.objects.filter(id=tenant_id).values_list("status", flat=True).first()
        )
    except Exception:  # noqa: BLE001
        logger.exception("Could not read status for tenant=%s", tenant_id)
        return None

    try:
        # Cache the empty string for "no such tenant" so a bogus id in a token
        # cannot make every request a database lookup.
        cache.set(key, status or "", _TTL_SECONDS)
    except Exception:  # noqa: BLE001
        pass
    return status


def tenant_is_active(tenant_id) -> bool:
    """True iff the tenant exists and is ACTIVE. Fails closed."""
    from .models import Tenant

    return tenant_status(tenant_id) == Tenant.Status.ACTIVE


def forget_tenant_status(tenant_id) -> None:
    """Drop the cached status — called by the ``post_save`` signal so a
    suspension takes effect on the very next request rather than within TTL."""
    try:
        caches["default"].delete(_KEY.format(tenant_id))
    except Exception:  # noqa: BLE001
        logger.exception("Could not invalidate cached status for tenant=%s", tenant_id)
