"""
Approval-escalation Celery-beat task.

This is the periodic sweep that keeps approvals moving when an approver sits on a
step past its timeout. It runs OFF-REQUEST on celery-beat, so it must NOT assume
any ambient tenant is bound: it asks the engine for every overdue PENDING step
across ALL tenants (the cross-tenant escape, valid off the request path) and then
hands each one to ``engine.escalate_step``, which binds that step's own tenant
and writes the immutable ``step.escalated`` audit record itself.

Registration: this task is wired onto celery-beat via
``CELERY_BEAT_SCHEDULE["approvals-escalate-overdue-routes"]`` in
``config/settings/base.py`` (do NOT duplicate that here). The dotted task name
``apps.approvals.tasks.escalate_overdue_routes`` must match that entry exactly.

The task is a thin, deterministic orchestrator — all state changes and auditing
live in the engine. It is directly callable synchronously (the tests call
``escalate_overdue_routes()``; ``.delay()`` is used in production).
"""
import logging

from celery import shared_task

from . import engine

logger = logging.getLogger("pms.approvals")


@shared_task
def escalate_overdue_routes():
    """Reassign every overdue PENDING approval step to its escalation target.

    Cross-tenant system sweep:
      * ``engine.overdue_pending_steps()`` returns the overdue PENDING steps
        across all tenants (off-request escape).
      * Each step is escalated via ``engine.escalate_step`` (tenant-bound and
        self-auditing). Every step is wrapped in its own try/except so one
        failing step never aborts the rest of the sweep — the failure is logged
        with the step id and the loop continues.

    Returns a small, deterministic summary dict::

        {"scanned": <n>, "escalated": <m>, "errors": <k>}

    where ``scanned`` is how many overdue steps were found, ``escalated`` counts
    the steps successfully processed by ``escalate_step``, and ``errors`` counts
    the steps whose escalation raised.
    """
    steps = engine.overdue_pending_steps()
    scanned = len(steps)
    escalated = 0
    errors = 0

    logger.info("approval escalation sweep starting: %d overdue step(s)", scanned)

    for step in steps:
        try:
            engine.escalate_step(step)
            escalated += 1
        except Exception:  # noqa: BLE001 — one bad step must not abort the sweep
            errors += 1
            logger.exception("failed to escalate approval step %s", step.id)

    summary = {"scanned": scanned, "escalated": escalated, "errors": errors}
    logger.info("approval escalation sweep complete: %s", summary)
    return summary
