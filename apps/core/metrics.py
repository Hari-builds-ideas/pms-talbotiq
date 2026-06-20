"""
Lightweight Prometheus-text metrics (BUILD_4 4.2) — a small custom exporter (no
new dependency; django-prometheus would need an image rebuild + multiprocess
wiring for gunicorn). Two kinds of signal:

* REQUEST counters — incremented per request by ``MetricsMiddleware`` into the
  Redis cache, so they aggregate across gunicorn workers/replicas (a per-process
  counter would undercount). Bucketed by a COARSE route class + status class so
  cardinality stays tiny (no ids, no per-tenant labels).
* on-demand GAUGES — queried live at scrape time: Celery queue depth (broker
  LLEN), AI job counts by status, token usage by agent, tenant count.

The AI/usage aggregates are SYSTEM-level totals across all tenants (no
per-tenant labels → no cross-tenant detail leaks). They use an explicitly
unscoped queryset: this is read-only system code, and the endpoint is
token-gated + internal (see ``MetricsView``).
"""
from __future__ import annotations

import logging

from django.core.cache import cache
from django.db.models import Count, QuerySet, Sum

logger = logging.getLogger("pms.metrics")

_REQ_PREFIX = "metrics:req"  # metrics:req:<route>:<status_class>
_REQ_TTL = 7 * 24 * 3600  # a week — counters are cumulative within that window


def route_class(path: str) -> str:
    """Coarse, low-cardinality bucket for a request path: the first segment after
    ``/api/`` (e.g. ``/api/reviews/123`` → ``reviews``), or a small fixed label."""
    p = path.strip("/")
    if p.startswith("api/"):
        parts = p.split("/")
        return parts[1] if len(parts) > 1 and parts[1] else "api_root"
    if p in ("healthz", "readyz", "metrics"):
        return p
    return "other"


def status_class(code: int) -> str:
    return f"{code // 100}xx"


def record_request(path: str, status_code: int) -> None:
    """Increment the cross-worker request counter for this request (best-effort —
    a cache hiccup must never break the response)."""
    key = f"{_REQ_PREFIX}:{route_class(path)}:{status_class(status_code)}"
    try:
        if cache.add(key, 0, _REQ_TTL):
            pass
        cache.incr(key)
    except Exception:  # noqa: BLE001 — metrics must never affect the request
        logger.debug("metrics: failed to record request for %s", key, exc_info=True)


def _unscoped(model) -> QuerySet:
    """A queryset that BYPASSES the tenant-scoped manager — system-level, read-only,
    aggregate-only. Used for cross-tenant TOTALS in the internal metrics export."""
    return QuerySet(model=model)


def _celery_queue_depth() -> int | None:
    from django.conf import settings

    try:
        import redis

        client = redis.from_url(settings.CELERY_BROKER_URL)
        return int(client.llen("celery"))  # the default Celery queue
    except Exception:  # noqa: BLE001
        logger.debug("metrics: celery queue depth unavailable", exc_info=True)
        return None


def _lines_for_requests() -> list[str]:
    out = []
    try:
        keys = cache.keys(f"{_REQ_PREFIX}:*")  # django-redis supports pattern keys
    except Exception:  # noqa: BLE001
        keys = []
    for full in sorted(keys):
        # full is the un-prefixed logical key (django-redis strips the prefix).
        logical = full.split(":")
        if len(logical) < 4:
            continue
        route, status = logical[-2], logical[-1]
        val = cache.get(f"{_REQ_PREFIX}:{route}:{status}") or 0
        out.append(f'pms_requests_total{{route="{route}",status="{status}"}} {int(val)}')
    return out


def render() -> str:
    """Render the full metrics exposition in Prometheus text format (0.0.4)."""
    from apps.ai.models import AIJob
    from apps.billing.models import TokenLedger
    from apps.tenancy.models import Tenant

    lines: list[str] = []

    lines.append("# HELP pms_requests_total HTTP requests by route class and status class.")
    lines.append("# TYPE pms_requests_total counter")
    req = _lines_for_requests()
    lines.extend(req or ['pms_requests_total{route="none",status="none"} 0'])

    lines.append("# HELP pms_celery_queue_depth Tasks waiting in the default Celery queue.")
    lines.append("# TYPE pms_celery_queue_depth gauge")
    depth = _celery_queue_depth()
    if depth is not None:
        lines.append(f"pms_celery_queue_depth {depth}")

    lines.append("# HELP pms_aijob_total Async AI jobs by status (all tenants).")
    lines.append("# TYPE pms_aijob_total gauge")
    for row in _unscoped(AIJob).values("status").annotate(n=Count("id")):
        lines.append(f'pms_aijob_total{{status="{row["status"]}"}} {row["n"]}')

    lines.append("# HELP pms_token_usage_total LLM tokens metered by agent (all tenants).")
    lines.append("# TYPE pms_token_usage_total counter")
    for row in _unscoped(TokenLedger).values("agent_code").annotate(t=Sum("total_tokens")):
        lines.append(f'pms_token_usage_total{{agent="{row["agent_code"]}"}} {int(row["t"] or 0)}')

    lines.append("# HELP pms_tenants_total Active tenants.")
    lines.append("# TYPE pms_tenants_total gauge")
    lines.append(f"pms_tenants_total {Tenant.objects.count()}")

    return "\n".join(lines) + "\n"
