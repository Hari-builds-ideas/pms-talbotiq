"""
Slack integration — best-effort notifications wired (via signals) to the Module-4
feedback-request and Module-5 approval touchpoints. The notifier is injected with a
FAKE that records sends; a Slack FAILURE never breaks the triggering action; an
unconfigured/disabled tenant is a clean no-op; secrets are read from env, never
stored/logged.
"""
import pytest
from django.test import override_settings

from apps.approvals.signals import approval_step_assigned, approval_step_escalated
from apps.feedback import services as feedback_services
from apps.feedback.models import FeedbackRequest
from apps.integrations import notifications
from apps.integrations.models import TenantIntegration
from apps.integrations.secrets import resolve_secret, secret_env_name
from apps.integrations.tests.fakes import reset_slack, set_slack_fail, slack_sent
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import FeedbackCycleFactory, TenantIntegrationFactory

pytestmark = pytest.mark.django_db

FAKE = "apps.integrations.tests.fakes.build_fake_slack_client"


def _enable_slack(tenant, *, channel="#perf"):
    with tenant_context(tenant):
        return TenantIntegration.objects.create(
            tenant_id=tenant.id, kind="SLACK", enabled=True, config={"channel": channel}
        )


# ── notify functions: record / no-op / failure-safe ──────────────────────────


@override_settings(SLACK_CLIENT_FACTORY=FAKE)
def test_notify_records_a_send_when_configured(tenant):
    reset_slack()
    _enable_slack(tenant)
    assert notifications.notify_feedback_request(str(tenant.id), relationship="PEER") is True
    sent = slack_sent()
    assert len(sent) == 1
    assert sent[0]["channel"] == "#perf"
    assert "PEER" in sent[0]["text"]


@override_settings(SLACK_CLIENT_FACTORY=FAKE)
def test_unconfigured_tenant_is_a_noop(tenant):
    reset_slack()
    # No Slack integration for this tenant → clean no-op (returns False, no send).
    assert notifications.notify_feedback_request(str(tenant.id), relationship="PEER") is False
    assert slack_sent() == []


@override_settings(SLACK_CLIENT_FACTORY=FAKE)
def test_disabled_integration_is_a_noop(tenant):
    reset_slack()
    with tenant_context(tenant):
        TenantIntegration.objects.create(tenant_id=tenant.id, kind="SLACK", enabled=False, config={})
    assert notifications.notify_feedback_request(str(tenant.id), relationship="PEER") is False
    assert slack_sent() == []


@override_settings(SLACK_CLIENT_FACTORY=FAKE)
def test_slack_failure_never_raises(tenant):
    reset_slack()
    _enable_slack(tenant)
    set_slack_fail(True)
    # A failing Slack must be swallowed (best-effort), not raised.
    assert notifications.notify_approval_assignment(
        str(tenant.id), route_id="r1", order=1, artifact_type="review"
    ) is False


# ── the Module-4 feedback touchpoint (real service → signal → receiver) ───────


@override_settings(SLACK_CLIENT_FACTORY=FAKE)
def test_feedback_request_triggers_a_notification(org):
    reset_slack()
    _enable_slack(org.tenant)
    cycle = FeedbackCycleFactory(subject=org.report)
    feedback_services.send_feedback_request(
        cycle=cycle, giver=org.peer, relationship="PEER", actor=org.manager
    )
    sent = slack_sent()
    assert len(sent) == 1 and "PEER" in sent[0]["text"]


@override_settings(SLACK_CLIENT_FACTORY=FAKE)
def test_feedback_request_survives_slack_failure(org):
    reset_slack()
    _enable_slack(org.tenant)
    set_slack_fail(True)
    cycle = FeedbackCycleFactory(subject=org.report)
    # The invitation is STILL created even though Slack is down (best-effort).
    request = feedback_services.send_feedback_request(
        cycle=cycle, giver=org.peer, relationship="PEER", actor=org.manager
    )
    assert request.pk is not None
    with tenant_context(org.tenant):
        assert FeedbackRequest.objects.filter(pk=request.pk).exists()
    assert slack_sent() == []  # the send failed, but the action succeeded


# ── the Module-5 approval touchpoints (signal → connected receiver) ───────────


@override_settings(SLACK_CLIENT_FACTORY=FAKE)
def test_approval_assignment_signal_notifies(tenant):
    reset_slack()
    _enable_slack(tenant)
    approval_step_assigned.send_robust(
        sender=None, tenant_id=str(tenant.id), route_id="route-1", order=1,
        artifact_type="review", approver_id=None,
    )
    sent = slack_sent()
    assert len(sent) == 1 and "Approval needed" in sent[0]["text"]


@override_settings(SLACK_CLIENT_FACTORY=FAKE)
def test_approval_escalation_signal_notifies(tenant):
    reset_slack()
    _enable_slack(tenant)
    approval_step_escalated.send_robust(
        sender=None, tenant_id=str(tenant.id), route_id="route-1", order=2,
    )
    sent = slack_sent()
    assert len(sent) == 1 and "escalated" in sent[0]["text"].lower()


# ── secrets: env-resolved, never stored/leaked ────────────────────────────────


def test_secret_is_resolved_from_env_not_stored(tenant, monkeypatch):
    integ = TenantIntegrationFactory(tenant=tenant, kind="SLACK", secret_ref="SLACK_WEBHOOK_TEST")
    # No env set → None (clean no-op path).
    monkeypatch.delenv("SLACK_WEBHOOK_TEST", raising=False)
    assert resolve_secret(integ) is None
    # Set the env → resolved by NAME; the token is never a DB column.
    monkeypatch.setenv("SLACK_WEBHOOK_TEST", "https://hooks.example/SECRET")
    assert resolve_secret(integ) == "https://hooks.example/SECRET"
    # The model stores only the env-var NAME, never the secret value.
    assert "SECRET" not in integ.secret_ref
    assert "SECRET" not in str(integ.config)


def test_secret_env_name_convention(tenant):
    integ = TenantIntegrationFactory(tenant=tenant, kind="JIRA", secret_ref="")
    # Falls back to <KIND>_TOKEN_<SLUG_UPPER> when no explicit ref.
    name = secret_env_name(integ)
    assert name.startswith("JIRA_TOKEN_")


def test_notification_text_never_contains_the_secret(tenant, monkeypatch):
    reset_slack()
    monkeypatch.setenv("SLACK_TOKEN_" + tenant.slug.upper().replace("-", "_"), "tok-SHHH")
    _enable_slack(tenant)
    with override_settings(SLACK_CLIENT_FACTORY=FAKE):
        notifications.notify_feedback_request(str(tenant.id), relationship="UPWARD")
    for msg in slack_sent():
        assert "SHHH" not in msg["text"]
