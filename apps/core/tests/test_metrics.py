"""
Metrics endpoint + exporter (BUILD_4 4.2).

`/metrics` is token-gated and fail-closed (no token configured → 404); the
exporter renders Prometheus text with cross-worker request counters (cache-backed)
+ live system aggregates (AI jobs, token usage, tenants) with NO per-tenant labels.
"""
import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.ai.models import AIJob
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory

pytestmark = pytest.mark.django_db

METRICS = "/metrics"


def test_metrics_disabled_without_token():
    # Default (test) settings leave METRICS_TOKEN unset → endpoint hidden.
    assert APIClient().get(METRICS).status_code == 404


@override_settings(METRICS_TOKEN="scrape-secret")
def test_metrics_requires_the_token():
    c = APIClient()
    assert c.get(METRICS).status_code == 401
    assert c.get(METRICS, HTTP_AUTHORIZATION="Bearer wrong").status_code == 401


@override_settings(METRICS_TOKEN="scrape-secret")
def test_metrics_renders_expected_series():
    t = TenantFactory()
    with tenant_context(t):
        AIJob.objects.create(
            tenant=t, agent_code="agent1", target_type="review",
            status=AIJob.Status.SUCCEEDED,
        )
    resp = APIClient().get(METRICS, HTTP_AUTHORIZATION="Bearer scrape-secret")
    assert resp.status_code == 200
    assert "text/plain" in resp["Content-Type"]
    body = resp.content.decode()
    assert '# TYPE pms_requests_total counter' in body
    assert 'pms_aijob_total{status="SUCCEEDED"}' in body
    assert "pms_tenants_total" in body


def test_request_counter_records_cross_worker_and_renders():
    from apps.core.metrics import record_request, render

    record_request("/api/reviews/123", 200)
    record_request("/api/reviews/456", 201)  # both 2xx
    record_request("/api/goals/", 404)
    body = render()
    assert 'pms_requests_total{route="reviews",status="2xx"} 2' in body
    assert 'pms_requests_total{route="goals",status="4xx"} 1' in body
