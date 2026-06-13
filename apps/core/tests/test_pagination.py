"""
Proof tests for the shared list pagination (FE #1).

Two shapes are exercised against REAL routes (production urlconf):
  * a PAGINATED list endpoint (the goals list) returns the
    ``{count, next, previous, results}`` envelope, honours ``?page_size=``, and
    keeps the caller's data scope INSIDE the envelope (an out-of-scope row never
    appears in ``results``);
  * a LEFT-AS-ARRAY endpoint (the integrations list) still returns a plain JSON
    array — pagination was applied surgically, not blanket.

Auth follows the standard pattern: ``issue_tokens_for_user`` → bearer token on an
``APIClient`` (see ``apps/succession/tests/test_api.py``).
"""
import pytest
from rest_framework.test import APIClient

from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, GoalFactory, UserFactory

pytestmark = pytest.mark.django_db

GOALS = "/api/goals/"
INTEGRATIONS = "/api/integrations/"


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def test_paginated_endpoint_returns_envelope_and_respects_page_size(org):
    """The goals list returns the standard page envelope and ``?page_size=1``
    yields a single result while ``count`` still reflects the full total."""
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        GoalFactory(employee=org.report, cycle=cycle, status="ACTIVE")
        GoalFactory(employee=org.report, cycle=cycle, status="ACTIVE")

    rep = _client_for(org.report)

    resp = rep.get(GOALS)
    assert resp.status_code == 200
    body = resp.json()
    # The envelope shape — exactly these top-level keys.
    assert set(body.keys()) == {"count", "next", "previous", "results"}
    assert body["count"] == 2
    assert len(body["results"]) == 2
    assert body["previous"] is None

    # ?page_size=1 → one row this page, the count still the full total, a next link.
    page1 = rep.get(f"{GOALS}?page_size=1").json()
    assert page1["count"] == 2
    assert len(page1["results"]) == 1
    assert page1["next"] is not None


def test_pagination_preserves_scope(org):
    """Pagination WRAPS the already-scoped queryset: an out-of-scope row (a
    peer's goal, outside the employee's OWN scope) is absent from ``results``."""
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        own = GoalFactory(employee=org.report, cycle=cycle, status="ACTIVE")
        peer_goal = GoalFactory(employee=org.peer, cycle=cycle, status="ACTIVE")

    resp = _client_for(org.report).get(GOALS)
    assert resp.status_code == 200
    body = resp.json()
    ids = {row["id"] for row in body["results"]}
    assert str(own.id) in ids
    assert str(peer_goal.id) not in ids
    assert body["count"] == 1


def test_left_as_array_endpoint_stays_a_plain_list(org):
    """A deliberately un-paginated list (integrations) still returns a plain JSON
    array, not the page envelope."""
    resp = _client_for(org.admin).get(INTEGRATIONS)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
