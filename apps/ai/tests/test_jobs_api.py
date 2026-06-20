"""
AI job poll API (BUILD_2 2.4) — ``GET /api/ai/jobs/<id>`` and ``?target=``.

RBAC/scope: a user polls only jobs THEY enqueued. Another user's job (same
tenant) and any cross-tenant job are 404 — never a 403 that would leak
existence. Unauthenticated is 401.
"""
import pytest
from rest_framework.test import APIClient

from apps.ai.models import AIJob
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db

JOBS = "/api/ai/jobs"


def _client(user):
    access, _ = issue_tokens_for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return c


def _job(tenant, requested_by, **kw):
    with tenant_context(tenant):
        return AIJob.objects.create(
            tenant=tenant,
            requested_by=requested_by,
            agent_code=kw.get("agent_code", "agent1"),
            target_type=kw.get("target_type", "review"),
            target_id=kw.get("target_id"),
            status=kw.get("status", AIJob.Status.SUCCEEDED),
        )


def test_requester_polls_own_job(org):
    job = _job(org.tenant, org.manager, status=AIJob.Status.SUCCEEDED)
    resp = _client(org.manager).get(f"{JOBS}/{job.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(job.id)
    assert body["status"] == "SUCCEEDED"
    assert body["agent_code"] == "agent1"


def test_another_user_in_tenant_cannot_see_the_job(org):
    job = _job(org.tenant, org.manager)
    # HRBP is in the same tenant but did not request this job → 404, not 403.
    resp = _client(org.hrbp).get(f"{JOBS}/{job.id}")
    assert resp.status_code == 404


def test_cross_tenant_job_is_404(org):
    other = TenantFactory(slug="other-jobs", name="Other")
    other_user = UserFactory(tenant=other, role="ADMIN", email="a@other-jobs.test")
    job = _job(other, other_user)
    resp = _client(org.manager).get(f"{JOBS}/{job.id}")
    assert resp.status_code == 404


def test_list_filters_to_target_and_own_jobs(org):
    import uuid

    target = uuid.uuid4()
    mine = _job(org.tenant, org.manager, target_id=target)
    _job(org.tenant, org.manager, target_id=uuid.uuid4())  # different target
    _job(org.tenant, org.hrbp, target_id=target)  # same target, another user

    resp = _client(org.manager).get(f"{JOBS}?target={target}")
    assert resp.status_code == 200
    ids = [row["id"] for row in resp.json()]
    assert ids == [str(mine.id)]  # only my job for that target


def test_unauthenticated_is_401(org):
    job = _job(org.tenant, org.manager)
    assert APIClient().get(f"{JOBS}/{job.id}").status_code == 401
