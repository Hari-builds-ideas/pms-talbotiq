"""
Integrations — per-tenant Jira + Slack configuration.

ONE model: ``TenantIntegration``. It holds NON-secret config (base_url, project,
channel, value field, …) and a ``secret_ref`` — the NAME of the environment
variable that holds the actual token — NEVER the token itself (see
``secrets.py`` + ``NEEDS_HARI_secrets.md``). An unconfigured/disabled tenant is a
clean no-op: Jira falls back to the Module-2 log-and-skip, Slack sends nothing.
"""
from django.db import models

from apps.tenancy.models import TenantScopedModel


class TenantIntegration(TenantScopedModel):
    """A tenant's configuration for one external system (Jira or Slack)."""

    class Kind(models.TextChoices):
        JIRA = "JIRA", "Jira"
        SLACK = "SLACK", "Slack"

    kind = models.CharField(max_length=8, choices=Kind.choices)
    enabled = models.BooleanField(default=False)
    #: Non-secret settings: Jira {base_url, email, project, value_field}; Slack
    #: {channel}. The token / webhook is NEVER stored here — see ``secret_ref``.
    config = models.JSONField(default=dict, blank=True)
    #: The NAME of the env var holding the secret token (NOT the token). Blank →
    #: the convention ``<KIND>_TOKEN_<TENANT_SLUG_UPPER>`` is used.
    secret_ref = models.CharField(max_length=128, blank=True)

    class Meta:
        db_table = "integrations_tenant_integration"
        ordering = ["kind"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "kind"], name="uq_integration_tenant_kind"),
        ]

    def __str__(self):
        return f"{self.kind} integration (tenant={self.tenant_id}, enabled={self.enabled})"
