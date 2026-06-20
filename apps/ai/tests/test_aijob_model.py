"""
AIJob tenant-scoping (BUILD_2 2.1).

AIJob is a ``TenantScopedModel``, so it inherits the same fail-closed isolation
as every other tenant row: reads are scoped to the bound tenant, a cross-tenant
read finds nothing, no bound tenant yields nothing (never the whole table), and a
cross-tenant write is refused. These guarantees are what let the worker bind the
job's tenant and trust the ORM (the worker has no request — proven in 2.2).
"""
import pytest

from apps.ai.models import AIJob
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _job(tenant, **kw):
    with tenant_context(tenant):
        return AIJob.objects.create(
            tenant=tenant,
            agent_code=kw.get("agent_code", "agent1"),
            target_type=kw.get("target_type", "review"),
            target_id=kw.get("target_id"),
        )


def test_aijob_reads_scoped_to_current_tenant():
    a = TenantFactory()
    b = TenantFactory()
    job_a = _job(a)
    job_b = _job(b)

    with tenant_context(a):
        assert set(AIJob.objects.values_list("id", flat=True)) == {job_a.id}
    with tenant_context(b):
        assert set(AIJob.objects.values_list("id", flat=True)) == {job_b.id}


def test_aijob_cross_tenant_read_is_impossible():
    a = TenantFactory()
    b = TenantFactory()
    job_b = _job(b)
    with tenant_context(a):
        assert not AIJob.objects.filter(id=job_b.id).exists()


def test_aijob_no_context_fails_closed():
    a = TenantFactory()
    _job(a)
    # Nothing bound -> zero rows. Never the whole table.
    assert AIJob.objects.count() == 0
    assert list(AIJob.objects.all()) == []


def test_aijob_cross_tenant_write_blocked():
    a = TenantFactory()
    b = TenantFactory()
    with tenant_context(a):
        with pytest.raises(PermissionError):
            AIJob.objects.create(tenant=b, agent_code="agent1", target_type="review")


def test_aijob_is_terminal_property():
    a = TenantFactory()
    job = _job(a)
    assert job.status == AIJob.Status.QUEUED
    assert not job.is_terminal
    for terminal in (AIJob.Status.SUCCEEDED, AIJob.Status.DEGRADED, AIJob.Status.FAILED):
        job.status = terminal
        assert job.is_terminal
    job.status = AIJob.Status.RUNNING
    assert not job.is_terminal
