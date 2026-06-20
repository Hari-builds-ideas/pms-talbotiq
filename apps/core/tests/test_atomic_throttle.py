"""
Atomic throttling + global AI ceiling + AIThrottle coverage (BUILD_3 3.2).

The entitlement throttles and the global LLM ceiling now use the atomic Lua
fixed-window counter, so concurrent requests across replicas can't overshoot the
limit at the edge. And every AI-triggering route carries the AI throttle bucket.
"""
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from django.core.cache import cache
from django.test import override_settings

from apps.billing import atomic
from apps.core.throttling import AIThrottle, AtomicAnonThrottle, RateLimited

pytestmark = pytest.mark.django_db


def _req(tenant_id, user_id):
    user = SimpleNamespace(is_authenticated=True, tenant_id=tenant_id, pk=user_id)
    return SimpleNamespace(user=user)


# ── the atomic primitive: no two callers get the same slot ────────────────────


def test_incr_window_is_atomic_no_duplicate_counts():
    key = f"test:incr:{uuid.uuid4().hex}"
    n = 64
    with ThreadPoolExecutor(max_workers=32) as pool:
        counts = list(pool.map(lambda _: atomic.incr_window(key, ttl_ms=60_000), range(n)))
    assert sorted(counts) == list(range(1, n + 1))  # every count unique → no overshoot


# ── the entitlement throttle ──────────────────────────────────────────────────


def test_throttle_enforces_limit(monkeypatch):
    monkeypatch.setattr(
        "apps.core.throttling.rate_limits_for",
        lambda tid: {"ai": "3/min", "tenant": "100/min", "user": "100/min"},
    )
    th = AIThrottle()
    req = _req(uuid.uuid4(), uuid.uuid4())
    assert th.allow_request(req, None) is True
    assert th.allow_request(req, None) is True
    assert th.allow_request(req, None) is True
    with pytest.raises(RateLimited):
        th.allow_request(req, None)  # the 4th overshoots the window → 429


def test_throttle_is_atomic_under_concurrency(monkeypatch):
    monkeypatch.setattr(
        "apps.core.throttling.rate_limits_for",
        lambda tid: {"ai": "5/min", "tenant": "100/min", "user": "100/min"},
    )
    # Same user (same window key); a fresh throttle instance per thread (no shared
    # instance state). Exactly 5 of 40 may pass.
    tid, uid = uuid.uuid4(), uuid.uuid4()

    def attempt(_):
        try:
            return AIThrottle().allow_request(_req(tid, uid), None)
        except RateLimited:
            return False

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(attempt, range(40)))
    assert sum(1 for r in results if r is True) == 5


# ── the global LLM ceiling ────────────────────────────────────────────────────


@override_settings(LLM_MAX_CALLS=3)
def test_global_ceiling_not_overshot_under_concurrency():
    from apps.ai.groq import _GLOBAL_CALL_KEY, GroqProvider
    from apps.ai.exceptions import LLMProviderError

    cache.delete(_GLOBAL_CALL_KEY)  # clean window

    def reserve(_):
        try:
            GroqProvider()._reserve_global()
            return True
        except LLMProviderError:
            return False

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(reserve, range(16)))
    assert sum(1 for r in results if r is True) == 3  # ceiling held exactly
    cache.delete(_GLOBAL_CALL_KEY)


# ── the login/auth anon throttle (atomic, IP-keyed) ───────────────────────────


def test_atomic_anon_throttle_enforces_limit_per_ip():
    th = AtomicAnonThrottle()
    th.rate = "3/min"
    req = SimpleNamespace(
        user=SimpleNamespace(is_authenticated=False),
        META={"REMOTE_ADDR": uuid.uuid4().hex},  # unique IP-ident → clean window
    )
    assert all(th.allow_request(req, None) for _ in range(3))
    assert th.allow_request(req, None) is False  # 4th burst blocked


# ── coverage: every AI-triggering route carries the AI throttle ───────────────


def test_every_ai_triggering_route_is_ai_throttled():
    from apps.ai.views import ChatView, NudgesView
    from apps.career.views import RoadmapEnrichView
    from apps.core.throttling import AIThrottle as _AI
    from apps.feedback.views import CycleSummarizeView
    from apps.jd.views import JDGenerateView
    from apps.reviews.views import ReviewRequestAIDraftView
    from apps.succession.views import PlanEnrichView

    ai_views = [
        ChatView, NudgesView, ReviewRequestAIDraftView, CycleSummarizeView,
        PlanEnrichView, JDGenerateView, RoadmapEnrichView,
    ]
    for view in ai_views:
        assert _AI in (view.throttle_classes or []), f"{view.__name__} missing AIThrottle"
