"""
Thin HTTP clients for Jira + Slack, and their injectable factories.

The clients are deliberately tiny and INJECTABLE: ``get_jira_client`` /
``get_slack_client`` resolve a factory from settings
(``JIRA_HTTP_CLIENT_FACTORY`` / ``SLACK_CLIENT_FACTORY``), so tests substitute a
deterministic FAKE that records/returns canned data and NO real network call ever
runs. Production uses the real clients below — which are INERT without a secret
(``resolve_secret`` → None → the caller treats the integration as unconfigured).
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from django.utils.module_loading import import_string

from .secrets import resolve_secret

logger = logging.getLogger("pms.integrations")


# ── Jira ─────────────────────────────────────────────────────────────────────


class JiraHTTPClient:
    """A minimal Jira REST client: fetch one issue and read a numeric field. The
    field path is ``config['value_field']`` (default ``fields.customfield_actual``;
    overridable per tenant). Inert without ``base_url`` + ``token``."""

    def __init__(self, *, base_url, email, token, value_field):
        self.base_url = (base_url or "").rstrip("/")
        self.email = email
        self.token = token
        self.value_field = value_field or "fields.customfield_actual"

    def fetch_issue_value(self, issue_key) -> Decimal:
        if not self.base_url or not self.token:
            raise RuntimeError("Jira client is not configured (no base_url/token).")
        import requests  # local import: only needed on the real path

        resp = requests.get(
            f"{self.base_url}/rest/api/3/issue/{issue_key}",
            auth=(self.email, self.token),
            headers={"Accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        node = data
        for part in self.value_field.split("."):
            node = node[part]
        return Decimal(str(node))


def build_jira_client(integration):
    cfg = integration.config or {}
    return JiraHTTPClient(
        base_url=cfg.get("base_url"),
        email=cfg.get("email"),
        token=resolve_secret(integration),
        value_field=cfg.get("value_field"),
    )


def get_jira_client(integration):
    """Resolve the Jira client factory (injectable via ``JIRA_HTTP_CLIENT_FACTORY``)."""
    factory = import_string(
        getattr(settings, "JIRA_HTTP_CLIENT_FACTORY", "apps.integrations.clients.build_jira_client")
    )
    return factory(integration)


# ── Slack ────────────────────────────────────────────────────────────────────


class SlackWebhookClient:
    """Posts a message to a Slack incoming webhook. The webhook URL is the SECRET
    (resolved from env), so this is inert (raises) without it — the caller's
    best-effort wrapper turns that into a logged no-op."""

    def __init__(self, *, webhook_url):
        self.webhook_url = webhook_url

    def post(self, channel, text):
        if not self.webhook_url:
            raise RuntimeError("Slack client is not configured (no webhook).")
        import requests  # local import: only needed on the real path

        payload = {"text": text}
        if channel:
            payload["channel"] = channel
        resp = requests.post(self.webhook_url, json=payload, timeout=5)
        resp.raise_for_status()


def build_slack_client(integration):
    # The webhook URL is a secret → resolved from env, never from config plaintext.
    return SlackWebhookClient(webhook_url=resolve_secret(integration))


def get_slack_client(integration):
    """Resolve the Slack client factory (injectable via ``SLACK_CLIENT_FACTORY``)."""
    factory = import_string(
        getattr(settings, "SLACK_CLIENT_FACTORY", "apps.integrations.clients.build_slack_client")
    )
    return factory(integration)
