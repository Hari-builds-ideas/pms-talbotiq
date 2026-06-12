from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integrations"
    verbose_name = "Integrations (Jira + Slack)"

    def ready(self):
        # Subscribe the Slack notifier to the core apps' notification signals
        # (one-way: core never imports integrations). Best-effort throughout.
        from apps.approvals.signals import (
            approval_step_assigned,
            approval_step_escalated,
        )
        from apps.feedback.signals import feedback_request_sent

        from . import receivers

        feedback_request_sent.connect(
            receivers.on_feedback_request_sent,
            dispatch_uid="integrations_feedback_request_sent",
        )
        approval_step_assigned.connect(
            receivers.on_approval_step_assigned,
            dispatch_uid="integrations_approval_step_assigned",
        )
        approval_step_escalated.connect(
            receivers.on_approval_step_escalated,
            dispatch_uid="integrations_approval_step_escalated",
        )
