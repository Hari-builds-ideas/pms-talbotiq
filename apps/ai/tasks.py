"""
The async AI dispatcher (BUILD_2) — ``run_agent_job``.

Each AI seam already has a ``@shared_task`` that binds the tenant, runs the
gateway, and locks the artifact PENDING_HUMAN_REVIEW (review draft, feedback
summary, succession enrich, JD generate, career enrich). What was missing is the
off-request orchestration + a status record the client can poll. ``run_agent_job``
provides exactly that, and NOTHING else about the AI changes:

1. bind the job's tenant inside the worker (it has no request),
2. load the :class:`AIJob` tenant-scoped — idempotent: a job that's already
   terminal is a no-op (safe against duplicate delivery / re-runs),
3. mark it RUNNING, dispatch to the seam task by ``agent_code``,
4. classify the seam's structured result onto the job:
   - success                       -> SUCCEEDED (artifact PENDING + metered)
   - no_provider / over budget /
     anonymity hold                -> DEGRADED  (graceful; artifact untouched)
   - provider error / preconditions-> FAILED    (artifact left in its pre-AI state)

The seam tasks own the safety properties (HITL gate, metering, anonymisation,
name-free succession, advisory career). Their own state guards make a second run
a no-op (the artifact is no longer in its initial state), so re-delivery cannot
double-meter the TokenLedger — proven by the idempotency test.

Retry: the gateway already does the transient back-off (Groq 429) WITHIN a single
call, so a seam ``provider_error`` is already post-retry and terminal — we land
FAILED rather than re-running the seam (whose state transitions are not
retry-idempotent). NOT_CONFIGURED / over-budget are terminal DEGRADED by
definition. See DECISIONS.md D4.
"""
from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from apps.tenancy.context import tenant_context

logger = logging.getLogger("pms.ai.jobs")

#: reason returned by a seam task -> (AIJob status, error_code). Reasons NOT in
#: here (provider_error, not_found, bad_state:*, actor_*, target_*, ...) are hard
#: failures -> FAILED with the reason as the error_code.
_DEGRADED = {
    "no_provider": "NOT_CONFIGURED",
    "budget_exceeded": "BUDGET_EXCEEDED",
    "anonymity_breach": "ANONYMITY_HOLD",
}


def _dispatch(job, actor_id):
    """Call the right seam task for ``job.agent_code`` and return
    ``(result_dict, success_key)``. The seam task binds its own tenant context,
    runs the gateway, and (on success) locks the artifact PENDING."""
    code = job.agent_code
    tid = str(job.tenant_id)
    target = str(job.target_id) if job.target_id else None

    if code == "agent1":
        from apps.reviews.tasks import draft_review_with_agent1

        return draft_review_with_agent1(tid, target, actor_id=actor_id), "drafted"
    if code == "agent3":
        from apps.feedback.tasks import summarize_feedback

        return summarize_feedback(tid, target, actor_id=actor_id), "summarized"
    if code == "agent4":
        from apps.succession.tasks import enrich_succession_with_agent4

        return enrich_succession_with_agent4(tid, target, actor_id=actor_id), "enriched"
    if code == "jd_generator":
        from apps.jd.tasks import generate_jd

        return generate_jd(tid, target, actor_id=actor_id), "generated"
    if code == "career_roadmap":
        from apps.career.tasks import generate_roadmap

        return (
            generate_roadmap(tid, target, job.params.get("target_ref"), actor_id=actor_id),
            "generated",
        )
    raise ValueError(f"run_agent_job: unknown agent_code {code!r}")


def _classify(result, success_key):
    """Map a seam result dict to ``(AIJob.status, error_code)``."""
    from apps.ai.models import AIJob

    if result.get(success_key):
        return AIJob.Status.SUCCEEDED, ""
    reason = result.get("reason") or "unknown"
    if reason in _DEGRADED:
        return AIJob.Status.DEGRADED, _DEGRADED[reason]
    return AIJob.Status.FAILED, reason.upper()[:32]


def _link_usage(job):
    """Best-effort link to the TokenLedger row the gateway metered for this run
    (the most recent for this tenant + agent at/after the job started). The
    artifact remains the authoritative source of the confidence/result."""
    from apps.billing.models import TokenLedger

    led = (
        TokenLedger.objects.filter(agent_code=job.agent_code)
        .order_by("-occurred_at")
        .first()
    )
    if led is not None and (job.started_at is None or led.occurred_at >= job.started_at):
        job.token_ledger = led


@shared_task(bind=True)
def run_agent_job(self, tenant_id, job_id):
    """Run the AI job ``job_id`` within ``tenant_id`` off the request thread."""
    from apps.ai.models import AIJob

    with tenant_context(tenant_id):
        job = AIJob.objects.filter(id=job_id).first()
        if job is None:
            logger.warning("run_agent_job: job %s not found in tenant %s", job_id, tenant_id)
            return {"job_id": str(job_id), "status": "not_found"}
        if job.is_terminal:
            # Duplicate delivery / manual re-run after completion: no-op (the work
            # already ran exactly once; the artifact is metered once).
            logger.info("run_agent_job: job %s already %s; skipping.", job.id, job.status)
            return {"job_id": str(job.id), "status": job.status}

        if job.status != AIJob.Status.RUNNING:
            job.status = AIJob.Status.RUNNING
            job.started_at = timezone.now()
            job.save(update_fields=["status", "started_at", "updated_at"])

        actor_id = str(job.requested_by_id) if job.requested_by_id else None
        try:
            result, success_key = _dispatch(job, actor_id)
        except Exception as exc:  # noqa: BLE001
            # A seam that raises (e.g. an uncaught validation error, or an unknown
            # agent_code) must NEVER strand the job RUNNING — record FAILED and
            # return. The seam's own guards mean the artifact is left pre-AI.
            logger.error(
                "run_agent_job: job %s (%s) dispatch raised; marking FAILED",
                job.id, job.agent_code, exc_info=True,
            )
            job.status = AIJob.Status.FAILED
            job.error_code = type(exc).__name__[:32]
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "error_code", "finished_at", "updated_at"])
            return {"job_id": str(job.id), "status": job.status, "error_code": job.error_code}
        status, error_code = _classify(result, success_key)

        job.status = status
        job.error_code = error_code
        job.finished_at = timezone.now()
        if status == AIJob.Status.SUCCEEDED:
            _link_usage(job)
        job.save(
            update_fields=[
                "status", "error_code", "finished_at", "confidence", "token_ledger", "updated_at",
            ]
        )
        logger.info(
            "run_agent_job: job %s (%s) -> %s%s",
            job.id, job.agent_code, job.status, f" [{error_code}]" if error_code else "",
        )
        return {"job_id": str(job.id), "status": job.status, "error_code": job.error_code}
