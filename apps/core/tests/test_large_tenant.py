"""
Large-tenant correctness (BUILD_1 1.4) — GATED behind ``@pytest.mark.large_tenant``.

Seeds one tenant with ~1.2k employees (+ a review and a goal each) and proves the
hot list endpoints stay correct at scale:

* the payload is PAGE-BOUNDED — a page returns ``page_size`` rows, never all N;
* the query count is O(1) in N — serving a page is a small constant number of
  queries, in BOTH the tenant scope (HRBP) and the big-team scope (Manager, whose
  ``employee_id__in`` filter spans all 1.2k reports);
* the org tree is SCOPE-BOUNDED — an Employee receives only their line (a handful
  of nodes), not the whole 1.2k-node tenant tree the directory once pulled.

Deselected by default (it bulk-seeds thousands of rows); run explicitly with::

    pytest -m large_tenant
"""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.goals.models import Goal
from apps.identity.models import User
from apps.identity.tokens import issue_tokens_for_user
from apps.reviews.models import Review
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory
from apps.testsupport.query_budget import count_queries

pytestmark = [pytest.mark.django_db, pytest.mark.large_tenant]

N = 1200
PAGE = 50
#: a page is a few queries (auth + the list + its select_related JOINs); the point
#: is it does NOT grow with N. A loose ceiling still rules out an O(N) regression.
QUERY_CEILING = 15


def _client(user):
    access, _ = issue_tokens_for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return c


def _seed_big_tenant(org):
    """Bulk-insert N employees (under org.manager) + a Review and a Goal each.

    bulk_create bypasses per-row save()/Argon2 — vital at N=1.2k — and we set
    ``tenant`` explicitly, all inside the tenant context.
    """
    with tenant_context(org.tenant.id):
        User.objects.bulk_create(
            [
                User(
                    tenant=org.tenant,
                    email=f"big{i}@acme.test",
                    role="EMPLOYEE",
                    manager=org.manager,
                    password="x",  # unhashed placeholder — these rows never authenticate
                )
                for i in range(N)
            ],
            batch_size=500,
        )
        emps = list(User.objects.filter(email__startswith="big"))
        cycle = CycleFactory(tenant=org.tenant)
        Review.objects.bulk_create(
            [Review(tenant=org.tenant, employee=e, reviewer=org.manager, cycle=cycle) for e in emps],
            batch_size=500,
        )
        Goal.objects.bulk_create(
            [
                Goal(
                    tenant=org.tenant,
                    employee=e,
                    created_by=org.manager,
                    cycle=cycle,
                    title="Scale goal",
                    weight=Decimal("10"),
                )
                for e in emps
            ],
            batch_size=500,
        )
    return cycle


def _assert_paginated_and_bounded(client, org, path, *, scope):
    with tenant_context(org.tenant.id):
        resp = client.get(path)
        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert body["count"] >= N, f"{path} ({scope}) count={body['count']} < {N}"
        assert len(body["results"]) == PAGE, (
            f"{path} ({scope}) returned {len(body['results'])} rows, not a bounded page of {PAGE}"
        )
        q = count_queries(lambda: client.get(path))
    assert q <= QUERY_CEILING, (
        f"{path} ({scope}) used {q} queries at N={N} — should be O(1), not O(N)"
    )


def test_hot_lists_paginate_and_stay_bounded_at_scale(org):
    """Reviews and Goals, in BOTH tenant scope (HRBP) and big-team scope (Manager,
    whose subtree spans all N reports), page correctly and in a constant query count."""
    _seed_big_tenant(org)
    for path in ("/api/reviews/?page_size=50", "/api/goals/?page_size=50"):
        _assert_paginated_and_bounded(_client(org.hrbp), org, path, scope="HRBP/tenant")
        _assert_paginated_and_bounded(_client(org.manager), org, path, scope="Manager/team")


def test_org_tree_is_scope_bounded(org):
    """The directory's tree is scope-applied: HRBP gets the whole tenant, an
    Employee only their own line — so the client never pulls 1.2k nodes for a leaf."""
    _seed_big_tenant(org)
    with tenant_context(org.tenant.id):
        hrbp_nodes = _client(org.hrbp).get("/api/org/tree").json()["nodes"]
        emp_nodes = _client(org.report).get("/api/org/tree").json()["nodes"]
    assert len(hrbp_nodes) >= N, f"HRBP tree has {len(hrbp_nodes)} nodes, expected the full tenant"
    assert len(emp_nodes) <= 25, (
        f"Employee tree has {len(emp_nodes)} nodes — should be just their line, not the tenant"
    )
