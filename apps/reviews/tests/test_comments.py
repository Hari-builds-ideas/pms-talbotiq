"""
Review section comments (BUILD_7 Feature A) — HTTP tests over the REAL
``/api/reviews/<pk>/comments`` routes.

Invariants:
  * commenting inherits the review's OWN scope exactly — you can only comment on
    a review you can already view (out-of-scope → 403, cross-tenant → 404), and
    commenting never broadens review visibility;
  * authorship is server-set; edit/delete are author-only (another's → 403);
  * one-level threading (a reply to a reply → 422);
  * tenant isolation (another tenant's review id → 404).
"""
import pytest
from rest_framework.test import APIClient

from apps.identity.tokens import issue_tokens_for_user
from apps.reviews.models import ReviewComment
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, ReviewFactory, UserFactory

pytestmark = pytest.mark.django_db

REVIEWS = "/api/reviews/"


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _review(org, *, employee=None, tenant=None):
    tenant = tenant or org.tenant
    employee = employee or org.report
    with tenant_context(tenant):
        cycle = CycleFactory(tenant=tenant, status="ACTIVE")
        return ReviewFactory(employee=employee, cycle=cycle, state="DRAFT")


def _comments_url(review):
    return f"{REVIEWS}{review.id}/comments"


# ── create / list ────────────────────────────────────────────────────────────


def test_manager_creates_and_lists_comment(org):
    review = _review(org)  # org.report's review — in the manager's subtree
    mgr = _client_for(org.manager)
    resp = mgr.post(_comments_url(review), {"body": "Strong quarter.", "section": "SUMMARY"}, format="json")
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["body"] == "Strong quarter."
    assert body["section"] == "SUMMARY"
    assert body["author"] == str(org.manager.id)
    assert body["author_name"]  # resolved, never a bare uuid
    assert body["edited_at"] is None

    listed = mgr.get(_comments_url(review)).json()
    assert any(c["id"] == body["id"] for c in listed)


def test_employee_comments_on_own_review(org):
    review = _review(org, employee=org.report)
    resp = _client_for(org.report).post(_comments_url(review), {"body": "Thanks!"}, format="json")
    assert resp.status_code == 201
    assert resp.json()["section"] is None  # general comment


def test_general_comment_section_optional(org):
    review = _review(org)
    resp = _client_for(org.hrbp).post(_comments_url(review), {"body": "Noted."}, format="json")
    assert resp.status_code == 201
    assert resp.json()["section"] is None


# ── edit / delete (author-only) ───────────────────────────────────────────────


def test_author_edits_own_comment(org):
    review = _review(org)
    mgr = _client_for(org.manager)
    cid = mgr.post(_comments_url(review), {"body": "v1"}, format="json").json()["id"]
    resp = mgr.patch(f"{_comments_url(review)}/{cid}", {"body": "v2 edited"}, format="json")
    assert resp.status_code == 200, resp.content
    assert resp.json()["body"] == "v2 edited"
    assert resp.json()["edited_at"] is not None


def test_author_deletes_own_comment_soft(org):
    review = _review(org)
    mgr = _client_for(org.manager)
    cid = mgr.post(_comments_url(review), {"body": "remove me"}, format="json").json()["id"]
    assert mgr.delete(f"{_comments_url(review)}/{cid}").status_code == 204
    assert all(c["id"] != cid for c in mgr.get(_comments_url(review)).json())  # gone from list
    with tenant_context(org.tenant):
        assert ReviewComment.objects.filter(id=cid).first() is None  # soft-deleted (manager hides)
        assert ReviewComment.all_objects.filter(id=cid).first() is not None  # row still there


def test_cannot_edit_or_delete_another_users_comment(org):
    review = _review(org)
    cid = _client_for(org.hrbp).post(_comments_url(review), {"body": "hrbp note"}, format="json").json()["id"]
    mgr = _client_for(org.manager)  # can SEE the review, but isn't the author
    assert mgr.patch(f"{_comments_url(review)}/{cid}", {"body": "hijack"}, format="json").status_code == 403
    assert mgr.delete(f"{_comments_url(review)}/{cid}").status_code == 403


# ── scope + tenant isolation (inherits the review's visibility exactly) ────────


def test_out_of_scope_cannot_comment_or_list(org):
    """A manager cannot see a peer's review (peer reports to HRBP, outside the
    manager's subtree) → 403 on both list and create, same as the review detail."""
    peer_review = _review(org, employee=org.peer)
    mgr = _client_for(org.manager)
    assert mgr.get(_comments_url(peer_review)).status_code == 403
    assert mgr.post(_comments_url(peer_review), {"body": "x"}, format="json").status_code == 403


def test_cross_tenant_review_is_404(org, other_tenant):
    outsider = UserFactory(tenant=other_tenant, role="EMPLOYEE", email="z@other.test")
    foreign_review = _review(org, employee=outsider, tenant=other_tenant)
    # org's HRBP (TENANT scope in THEIR tenant) can't reach another tenant's review.
    resp = _client_for(org.hrbp).get(_comments_url(foreign_review))
    assert resp.status_code == 404
    assert _client_for(org.hrbp).post(
        _comments_url(foreign_review), {"body": "x"}, format="json"
    ).status_code == 404


# ── one-level threading ────────────────────────────────────────────────────────


def test_reply_is_one_level(org):
    review = _review(org)
    mgr = _client_for(org.manager)
    top = mgr.post(_comments_url(review), {"body": "top"}, format="json").json()
    reply = mgr.post(_comments_url(review), {"body": "reply", "parent": top["id"]}, format="json")
    assert reply.status_code == 201
    assert reply.json()["parent"] == top["id"]
    # a reply to the reply → 422 (one level only)
    deep = mgr.post(
        _comments_url(review), {"body": "reply to reply", "parent": reply.json()["id"]}, format="json"
    )
    assert deep.status_code == 422


def test_reply_parent_from_another_review_is_404(org):
    r1, r2 = _review(org), _review(org)
    mgr = _client_for(org.manager)
    foreign_parent = mgr.post(_comments_url(r1), {"body": "on r1"}, format="json").json()["id"]
    # parent belongs to r1, but we post under r2 → the scoped same-review lookup 404s.
    resp = mgr.post(_comments_url(r2), {"body": "x", "parent": foreign_parent}, format="json")
    assert resp.status_code == 404


def test_unauthenticated_is_401(org):
    review = _review(org)
    assert APIClient().get(_comments_url(review)).status_code == 401
