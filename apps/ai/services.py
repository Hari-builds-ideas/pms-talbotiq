"""
AI job services (BUILD_2) — the one way a seam goes async.

``enqueue_agent_job`` creates a tenant-scoped :class:`AIJob` (QUEUED) and hands
the work to the ``run_agent_job`` Celery task, returning immediately. The calling
endpoint returns ``202 Accepted`` with the job id; the client polls
``GET /api/ai/jobs/<id>``. In tests (``CELERY_TASK_ALWAYS_EAGER``) the task runs
inline, so the job is already terminal when the request returns — but the
endpoint still just enqueues + returns the job (fire-and-poll), never inspecting
the result. The tenant is taken from the actor (server-set, never the client).
"""
from __future__ import annotations

from .models import AIJob


def enqueue_agent_job(*, actor, agent_code, target_type, target_id=None, params=None):
    """Create a QUEUED AIJob for ``actor``'s tenant and enqueue ``run_agent_job``.

    Returns the AIJob. Import the task lazily so this module stays import-light
    and the Celery edge is one-way (services -> task, never back)."""
    from .tasks import run_agent_job

    job = AIJob.objects.create(
        tenant=actor.tenant,
        requested_by=actor,
        agent_code=agent_code,
        target_type=target_type,
        target_id=target_id,
        params=params or {},
        status=AIJob.Status.QUEUED,
    )
    run_agent_job.delay(str(actor.tenant_id), str(job.id))
    return job
