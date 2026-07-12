"""
Atomic, cross-replica-safe counters via Redis Lua (BUILD_3).

A check-then-increment done in two round trips lets two replicas both read
``current < limit`` and both increment — overshooting the cap at the boundary
(the documented MVP gap, billing/services.py). A Lua script runs the
read + compare + increment + TTL as ONE atomic server-side step, so the cap holds
no matter how many replicas reserve at once.

Keys are the project's tenant-namespaced cache keys, passed through
``cache.make_key`` so they match exactly what django-redis would store (same
prefix + version), keeping the counter consistent with the rest of the cache.
"""
from __future__ import annotations

import hashlib

from django.core.cache import cache
from django_redis import get_redis_connection
from redis.exceptions import NoScriptError

# Reserve one unit iff strictly under ``limit``. Returns the new count (>= 1) on
# success, or -1 if already at/over the limit (NO increment happened). The window
# TTL is set on the FIRST increment only — the period-stamped key gives the
# fixed-window reset, the TTL is cleanup.
_RESERVE = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
local limit = tonumber(ARGV[1])
if current >= limit then
  return -1
end
local v = redis.call('INCR', KEYS[1])
if v == 1 then
  redis.call('PEXPIRE', KEYS[1], ARGV[2])
end
return v
"""

# Refund one unit, never below zero. Returns the new count.
_RELEASE = """
local v = tonumber(redis.call('GET', KEYS[1]) or '0')
if v > 0 then
  return redis.call('DECR', KEYS[1])
end
return 0
"""

# Increment one unit unconditionally, setting the window TTL on the first hit.
# Returns the new count (the caller compares it to the limit AFTER). Used by the
# fixed-window throttle/ceiling counters where the limit is enforced post-incr.
_INCR_WINDOW = """
local v = redis.call('INCR', KEYS[1])
if v == 1 then
  redis.call('PEXPIRE', KEYS[1], ARGV[1])
end
return v
"""


def _conn():
    return get_redis_connection("default")


def _full_key(logical_key: str) -> str:
    return cache.make_key(logical_key)


#: source -> SHA1, so calls use EVALSHA (Redis caches the script body once) instead
#: of shipping the whole Lua text every time.
_SHAS: dict[str, str] = {}


def _eval(script: str, numkeys: int, *args):
    """Run ``script`` via EVALSHA for speed, recovering with EVAL on NOSCRIPT — the
    case where Redis has no cached copy of the script (a fresh server, a restart, or
    ``SCRIPT FLUSH``). EVAL re-primes the cache, so the next EVALSHA hits. This makes
    the atomic counters survive a Redis restart with no boot-time SCRIPT LOAD needed.
    """
    conn = _conn()
    sha = _SHAS.get(script)
    if sha is None:
        sha = _SHAS[script] = hashlib.sha1(script.encode()).hexdigest()
    try:
        return conn.evalsha(sha, numkeys, *args)
    except NoScriptError:
        return conn.eval(script, numkeys, *args)


def reserve(logical_key: str, *, limit: int, ttl_ms: int) -> int:
    """Atomically reserve one unit under ``limit``. Returns the reserved count
    (>= 1) or -1 if the limit is already reached (nothing reserved)."""
    return int(_eval(_RESERVE, 1, _full_key(logical_key), int(limit), int(ttl_ms)))


def release(logical_key: str) -> int:
    """Atomically refund one unit (never below zero). Returns the new count."""
    return int(_eval(_RELEASE, 1, _full_key(logical_key)))


def incr_window(logical_key: str, *, ttl_ms: int) -> int:
    """Atomically increment a fixed-window counter (TTL set on first hit) and
    return the new count. The caller enforces the limit against the return."""
    return int(_eval(_INCR_WINDOW, 1, _full_key(logical_key), int(ttl_ms)))


def reset_window(logical_key: str) -> None:
    """Drop a fixed-window counter early (e.g. clear a login-lockout counter after
    a successful login). Best-effort: a Redis outage must not break the caller —
    the same soft posture as the budget fail-open."""
    try:
        get_redis_connection("default").delete(_full_key(logical_key))
    except Exception:  # noqa: BLE001
        pass
