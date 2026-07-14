"""
run_agent_job (BUILD_2 2.2) — the async dispatcher, exercised with the
FakeLLMProvider (ZERO Groq). Uses the review seam (Agent 1) as the reference.

Proves the async move preserves every safety property and lands the job status
correctly:
* SUCCEEDED — the artifact ends PENDING_HUMAN_REVIEW and is metered once;
* FAILED — a provider error leaves the artifact in its pre-result state (no
  half-written PENDING draft) and the job FAILED;
* DEGRADED — no provider (NOT_CONFIGURED) and over-budget (BUDGET_EXCEEDED) are
  graceful: the artifact is untouched, no exception escapes, no fabricated draft;
* the worker CANNOT touch another tenant's job (tenant bound from the job);
* idempotent — a second run is a no-op and does NOT double-meter the ledger.
"""
import pytest
from django.test import override_settings

from apps.ai import providers
from apps.ai.models import AIJob
from apps.ai.tasks import run_agent_job
from apps.billing.exceptions import BudgetExceeded
from apps.billing.models import TokenLedger
from apps.reviews.models import Review
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, ReviewFactory, TenantFactory

pytestmark = pytest.mark.django_db

WIRED = dict(
    LLM_PROVIDER="apps.ai.providers.FakeLLMProvider",
    REVIEW_ASSISTANT_PROVIDER="apps.ai.agents.review.ReviewAssistantProvider",
)


def _draft_review(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        return ReviewFactory(employee=org.report, cycle=cycle, state="DRAFT")


def _job_for(org, review, **kw):
    with tenant_context(org.tenant):
        return AIJob.objects.create(
            tenant=org.tenant,
            requested_by=org.manager,
            agent_code="agent1",
            target_type="review",
            target_id=review.id,
            **kw,
        )


def _ledger_count(org):
    with tenant_context(org.tenant):
        return TokenLedger.objects.filter(agent_code="agent1").count()


@override_settings(**WIRED)
def test_succeeds_artifact_pending_and_metered_once(org):
    review = _draft_review(org)
    job = _job_for(org, review)

    out = run_agent_job(str(org.tenant.id), str(job.id))

    assert out["status"] == AIJob.Status.SUCCEEDED
    with tenant_context(org.tenant):
        job.refresh_from_db()
        review.refresh_from_db()
    assert job.status == AIJob.Status.SUCCEEDED
    assert job.started_at is not None and job.finished_at is not None
    assert job.token_ledger_id is not None  # usage linked
    assert str(job.result_id) == str(review.id)  # produced artifact recorded
    assert review.state == Review.State.PENDING_HUMAN_REVIEW  # HITL lock preserved
    assert _ledger_count(org) == 1  # metered exactly once


@override_settings(**WIRED)
def test_provider_error_fails_job_and_leaves_artifact_unpublished(org):
    # A fake builder that raises -> gateway PROVIDER_ERROR -> AgentUnavailable.
    def boom(prompt, model):
        raise RuntimeError("provider blew up")

    providers.register_fake_output("agent1", boom)
    try:
        review = _draft_review(org)
        job = _job_for(org, review)
        out = run_agent_job(str(org.tenant.id), str(job.id))
    finally:
        from apps.ai.agents import review as review_agent  # restore the good builder
        providers.register_fake_output("agent1", review_agent._fake)

    assert out["status"] == AIJob.Status.FAILED
    with tenant_context(org.tenant):
        job.refresh_from_db()
        review.refresh_from_db()
    assert job.status == AIJob.Status.FAILED
    assert job.error_code == "PROVIDER_ERROR"
    # No fabricated draft: the review is NOT locked PENDING.
    assert review.state != Review.State.PENDING_HUMAN_REVIEW


@override_settings(**WIRED)
def test_soft_time_limit_marks_job_failed_timeout(org, monkeypatch):
    # FIX-ROUND: a seam that runs past the Celery soft time limit raises
    # SoftTimeLimitExceeded INSIDE the task — it must land the job FAILED/TIMEOUT
    # (not stranded RUNNING), so the client's spinner resolves to the retry banner.
    from celery.exceptions import SoftTimeLimitExceeded

    import apps.ai.tasks as tasks_mod

    def _timeout(job, actor_id):
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(tasks_mod, "_dispatch", _timeout)
    review = _draft_review(org)
    job = _job_for(org, review)
    out = run_agent_job(str(org.tenant.id), str(job.id))

    assert out["status"] == AIJob.Status.FAILED and out["error_code"] == "TIMEOUT"
    with tenant_context(org.tenant):
        job.refresh_from_db()
        review.refresh_from_db()
    assert job.status == AIJob.Status.FAILED and job.error_code == "TIMEOUT"
    assert job.finished_at is not None  # terminal — never stranded RUNNING
    assert review.state != Review.State.PENDING_HUMAN_REVIEW  # no fabricated draft


def test_not_configured_degrades_job_and_leaves_review_in_draft(org):
    # No WIRED override -> default NotConfiguredProvider -> no_provider.
    review = _draft_review(org)
    job = _job_for(org, review)

    out = run_agent_job(str(org.tenant.id), str(job.id))

    assert out["status"] == AIJob.Status.DEGRADED
    with tenant_context(org.tenant):
        job.refresh_from_db()
        review.refresh_from_db()
    assert job.status == AIJob.Status.DEGRADED
    assert job.error_code == "NOT_CONFIGURED"
    assert review.state == Review.State.DRAFT  # untouched
    assert _ledger_count(org) == 0  # nothing metered


@override_settings(**WIRED)
def test_over_budget_degrades_job(org, monkeypatch):
    # Force the gateway's pre-call budget reserve to refuse -> BUDGET_EXCEEDED.
    def _over_budget(*a, **k):
        raise BudgetExceeded(agent_code="agent1", window="DAILY", limit=0)

    monkeypatch.setattr("apps.ai.gateway.check_and_reserve_budget", _over_budget)
    review = _draft_review(org)
    job = _job_for(org, review)

    out = run_agent_job(str(org.tenant.id), str(job.id))

    assert out["status"] == AIJob.Status.DEGRADED
    with tenant_context(org.tenant):
        job.refresh_from_db()
    assert job.error_code == "BUDGET_EXCEEDED"
    assert _ledger_count(org) == 0  # over budget -> never metered


@override_settings(**WIRED)
def test_global_ceiling_degrades_job_not_fails(org):
    # Finding A: hitting the run-wide LLM call ceiling is a graceful limit
    # (DEGRADED / BUDGET_EXCEEDED), NOT a hard provider failure (FAILED /
    # PROVIDER_ERROR). A builder that raises the ceiling error must land DEGRADED,
    # leave the review in DRAFT, and meter nothing (the ceiling fires pre-call).
    from apps.ai.exceptions import LLMGlobalCeilingError

    def ceiling(prompt, model):
        raise LLMGlobalCeilingError("Global LLM call ceiling (1) reached for this run.")

    providers.register_fake_output("agent1", ceiling)
    try:
        review = _draft_review(org)
        job = _job_for(org, review)
        out = run_agent_job(str(org.tenant.id), str(job.id))
    finally:
        from apps.ai.agents import review as review_agent  # restore the good builder
        providers.register_fake_output("agent1", review_agent._fake)

    assert out["status"] == AIJob.Status.DEGRADED
    with tenant_context(org.tenant):
        job.refresh_from_db()
        review.refresh_from_db()
    assert job.status == AIJob.Status.DEGRADED
    assert job.error_code == "BUDGET_EXCEEDED"  # graceful, NOT PROVIDER_ERROR
    # No fabricated draft: the review is NOT locked PENDING (the seam already moved
    # it DRAFT→AI_DRAFTING before the gateway call, exactly as for any AI failure).
    assert review.state != Review.State.PENDING_HUMAN_REVIEW
    assert _ledger_count(org) == 0  # ceiling fired before any real call


@override_settings(**WIRED)
def test_worker_cannot_touch_another_tenants_job(org):
    # A job that belongs to tenant B...
    other = TenantFactory(slug="other", name="Other")
    with tenant_context(other):
        job_b = AIJob.objects.create(
            tenant=other, agent_code="agent1", target_type="review", target_id=None
        )
    # ...is invisible when the worker binds tenant A: a no-op, never processed.
    out = run_agent_job(str(org.tenant.id), str(job_b.id))
    assert out["status"] == "not_found"
    with tenant_context(other):
        job_b.refresh_from_db()
    assert job_b.status == AIJob.Status.QUEUED  # untouched


@override_settings(**WIRED)
def test_idempotent_second_run_is_noop_no_double_meter(org):
    review = _draft_review(org)
    job = _job_for(org, review)

    first = run_agent_job(str(org.tenant.id), str(job.id))
    second = run_agent_job(str(org.tenant.id), str(job.id))

    assert first["status"] == AIJob.Status.SUCCEEDED
    assert second["status"] == AIJob.Status.SUCCEEDED  # terminal -> returned as-is
    assert _ledger_count(org) == 1  # still metered exactly once
