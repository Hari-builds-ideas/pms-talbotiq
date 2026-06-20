"""
BUILD_2 2.5 — the async sweep: a converted seam ENQUEUES, it does NOT run the
gateway in the request thread.

Every seam routes through ``enqueue_agent_job`` → ``run_agent_job.delay`` — one
choke point — so we prove it on the reference seam (review draft) with the
strongest possible assertion: with ``CELERY_TASK_ALWAYS_EAGER=False`` the
``.delay()`` only queues, so the endpoint must return ``202`` with the artifact
UNTOUCHED (still DRAFT, not PENDING) and NOTHING metered — i.e. the LLM gateway
was never reached before the response. The feedback close path additionally
shows its synchronous transition still happens while the summary is deferred.

Chat is the deliberate synchronous exception (short, interactive); it stays
sync + RBAC-bound + write-blocked with the gateway's own graceful degradation
(503/429), and is covered by ``test_chat.py``.
"""
import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.ai.models import AIJob
from apps.billing.models import TokenLedger
from apps.feedback.models import FeedbackCycle
from apps.identity.tokens import issue_tokens_for_user
from apps.reviews.models import Review
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, FeedbackCycleFactory, ReviewFactory

pytestmark = pytest.mark.django_db

WIRED = dict(
    LLM_PROVIDER="apps.ai.providers.FakeLLMProvider",
    REVIEW_ASSISTANT_PROVIDER="apps.ai.agents.review.ReviewAssistantProvider",
    FEEDBACK_SUMMARIZER_PROVIDER="apps.ai.agents.feedback.FeedbackSummarizerProvider",
)


def _client(user):
    access, _ = issue_tokens_for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return c


@override_settings(CELERY_TASK_ALWAYS_EAGER=False, **WIRED)
def test_review_seam_enqueues_and_never_runs_gateway_in_request(org, monkeypatch):
    # Spy on the dispatch enqueue: it must be called, but the task must NOT run.
    calls = []
    monkeypatch.setattr("apps.ai.tasks.run_agent_job.delay", lambda *a, **k: calls.append(a))
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        review = ReviewFactory(employee=org.report, cycle=cycle, state="DRAFT")

    resp = _client(org.manager).post(f"/api/reviews/{review.id}/request-ai-draft")

    assert resp.status_code == 202
    assert len(calls) == 1  # enqueued exactly once
    with tenant_context(org.tenant):
        review.refresh_from_db()
        assert review.state == Review.State.DRAFT  # NOT drafted in-request
        assert TokenLedger.objects.filter(agent_code="agent1").count() == 0  # gateway never reached
        assert AIJob.objects.get(id=resp.json()["id"]).status == AIJob.Status.QUEUED


@override_settings(CELERY_TASK_ALWAYS_EAGER=False, **WIRED)
def test_feedback_close_is_sync_but_summary_is_deferred(org, monkeypatch):
    calls = []
    monkeypatch.setattr("apps.ai.tasks.run_agent_job.delay", lambda *a, **k: calls.append(a))
    with tenant_context(org.tenant):
        cycle = FeedbackCycleFactory(subject=org.report, status="COLLECTING")

    resp = _client(org.manager).post(f"/api/feedback/cycles/{cycle.id}/close")

    assert resp.status_code == 200
    # The CLOSE transition is synchronous...
    assert resp.json()["cycle"]["status"] == "CLOSED"
    # ...but the Agent-3 summary is deferred (enqueued), not run in-request.
    assert len(calls) == 1
    assert resp.json()["job"]["status"] == AIJob.Status.QUEUED
    with tenant_context(org.tenant):
        assert TokenLedger.objects.filter(agent_code="agent3").count() == 0
