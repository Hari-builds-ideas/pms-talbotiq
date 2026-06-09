"""
Celery entry point for the deterministic scoring engine.

The actual math lives in :mod:`apps.goals.scoring.engine`; this module is only the
async seam. The engine binds the tenant itself (it runs off the request path), so
the task signature carries the ids explicitly.

Synchronous vs async: ``recompute_cycle_scores`` is a plain function wrapped by
``@shared_task``. Calling it directly —

    recompute_cycle_scores(tenant_id, cycle_id)

runs the engine SYNCHRONOUSLY in the caller's process (this is what the tests and
the API trigger view do, so a freshly-saved measurement is scored inline). In
production a worker picks it up via ``recompute_cycle_scores.delay(tenant_id,
cycle_id)``. Same code path, same deterministic result either way.

Scope note: the Jira sync task is intentionally NOT here — it lives in its own
module owned by another agent.
"""
from celery import shared_task

from .scoring.engine import compute_cycle_scores


@shared_task
def recompute_cycle_scores(tenant_id, cycle_id):
    """Recompute and store all CycleScores for a (tenant, cycle).

    Returns the list of stored CycleScore rows (see ``compute_cycle_scores``).
    Idempotent: re-running produces identical score fields and no duplicate rows.
    """
    return compute_cycle_scores(tenant_id, cycle_id)
