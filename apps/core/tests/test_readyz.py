"""Tests for the ``/readyz`` readiness probe and the liveness/readiness split.

These run inside the Docker stack where MySQL, Redis, and the Celery broker are
all reachable and migrations are applied, so the happy-path probe is green.
"""
from unittest import mock

import pytest
from health_check.db.backends import DatabaseBackend
from health_check.exceptions import ServiceUnavailable


@pytest.mark.django_db
def test_readyz_returns_200_when_all_dependencies_up(client):
    """With every dependency reachable, /readyz reports ready with a 200."""
    resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    # Every reported check should be up.
    assert all(state == "up" for state in body["checks"].values())


@pytest.mark.django_db
def test_readyz_returns_503_when_a_dependency_is_down(client):
    """If any backend fails, /readyz reports 503 and flags that check down."""
    with mock.patch.object(
        DatabaseBackend, "check_status", side_effect=ServiceUnavailable("db down")
    ):
        resp = client.get("/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not ready"
    assert body["checks"]["DatabaseBackend"] == "down"


@pytest.mark.django_db
def test_healthz_stays_pure_liveness_even_when_a_dependency_is_down(client):
    """Liveness must not run dependency checks: /healthz stays 200 even while a
    backend the readiness probe relies on is failing."""
    with mock.patch.object(
        DatabaseBackend, "check_status", side_effect=ServiceUnavailable("db down")
    ):
        resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "pms"}
