"""
Session/device + lockout helpers (PHASE2 L1.3) — ADDITIVE on top of the existing
JWT scheme (rotation + blacklist untouched).

* Device sessions: one row per login; its id rides the JWTs as the ``did`` claim
  and is re-checked at refresh time, so revoking a session kills it within the
  access-token lifetime.
* Login history: every auth event recorded (tenant-scoped, best-effort ip/UA).
* Account lockout: an atomic fixed-window attempt counter per (tenant, email) —
  the same Redis primitive the AI budgets use. Counts ATTEMPTS (reset on
  success), keyed by the attempted email whether or not the account exists, so
  the response never leaks account existence.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.utils import timezone

from apps.billing import atomic

from .models import DeviceSession, LoginEvent

logger = logging.getLogger("pms.identity")


# ── request metadata (best-effort) ───────────────────────────────────────────
def client_ip(request) -> str | None:
    fwd = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    return fwd or request.META.get("REMOTE_ADDR") or None


def client_ua(request) -> str:
    return (request.META.get("HTTP_USER_AGENT") or "")[:512]


# ── login history ─────────────────────────────────────────────────────────────
def log_event(*, tenant_id, email: str, event: str, user=None, request=None) -> None:
    """Record a login-history row. Never raises — history must not break auth."""
    try:
        LoginEvent.objects.create(
            tenant_id=tenant_id,
            user=user,
            email=(email or "")[:254],
            event=event,
            ip=client_ip(request) if request is not None else None,
            user_agent=client_ua(request) if request is not None else "",
        )
    except Exception:  # noqa: BLE001
        logger.exception("login-event write failed (event=%s)", event)


# ── account lockout (fixed window, atomic) ────────────────────────────────────
def _lockout_key(tenant_slug: str, email: str) -> str:
    return f"lockout:{tenant_slug}:{(email or '').lower()}"


def register_attempt(tenant_slug: str, email: str) -> bool:
    """Count a login attempt; True when the account is now over the limit.
    Fail-open on Redis trouble (the per-IP anon throttle still applies)."""
    limit = int(getattr(settings, "LOGIN_LOCKOUT_ATTEMPTS", 8))
    window_ms = int(getattr(settings, "LOGIN_LOCKOUT_WINDOW_SECONDS", 900)) * 1000
    if limit <= 0:
        return False
    try:
        count = atomic.incr_window(_lockout_key(tenant_slug, email), ttl_ms=window_ms)
    except Exception:  # noqa: BLE001 — Redis down → don't lock everyone out
        return False
    return count > limit


def clear_attempts(tenant_slug: str, email: str) -> None:
    """A successful login clears the window."""
    atomic.reset_window(_lockout_key(tenant_slug, email))


# ── device sessions ───────────────────────────────────────────────────────────
def start_device_session(request, user) -> DeviceSession:
    """Create the session row for a fresh login; its id becomes the ``did`` claim."""
    return DeviceSession.objects.create(
        tenant_id=user.tenant_id,
        user=user,
        ip=client_ip(request) if request is not None else None,
        user_agent=client_ua(request) if request is not None else "",
    )


def revoke_session(session: DeviceSession, *, request=None) -> None:
    """Mark a session revoked (enforced at the next refresh) + history row."""
    if session.revoked_at is None:
        session.revoked_at = timezone.now()
        session.save(update_fields=["revoked_at"])
    log_event(
        tenant_id=session.tenant_id,
        email=session.user.email,
        event=LoginEvent.Event.SESSION_REVOKED,
        user=session.user,
        request=request,
    )


def _unscoped_session_qs():
    """Refresh-time lookups run BEFORE a tenant is bound (the refresh request
    carries no access token), so the fail-closed manager would hide every row and
    revocation would silently not enforce. Mirror the bootstrap pattern of
    ``UserManager.get_by_natural_id_unscoped``: a raw queryset used ONLY for a
    single unguessable-UUID lookup — never a list surface."""
    from django.db import models as dj_models

    return dj_models.QuerySet(DeviceSession)


def session_is_revoked(did: str | None) -> bool:
    """True when ``did`` names a revoked session. A token WITHOUT a did claim
    (pre-feature tokens) is not rejected — additive rollout."""
    if not did:
        return False
    try:
        row = _unscoped_session_qs().filter(id=did).only("revoked_at").first()
    except Exception:  # noqa: BLE001 — malformed did → treat as no claim
        return False
    return bool(row and row.revoked_at is not None)


def touch_session(did: str | None) -> None:
    """Bump last_seen on refresh (best-effort; unscoped single-row update)."""
    if not did:
        return
    try:
        _unscoped_session_qs().filter(id=did).update(last_seen=timezone.now())
    except Exception:  # noqa: BLE001
        pass
