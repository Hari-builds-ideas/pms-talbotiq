"""
Deterministic in-repo FAKES for the Jira + Slack clients, injected via the
``JIRA_HTTP_CLIENT_FACTORY`` / ``SLACK_CLIENT_FACTORY`` settings in tests. NO real
network call ever runs. Module-level recorders let tests assert what was sent /
returned; reset them at the top of each test.
"""
from __future__ import annotations

from decimal import Decimal

# ── Slack fake ────────────────────────────────────────────────────────────────

_SLACK_SENT: list[dict] = []
_SLACK_FAIL = {"on": False}


class _FakeSlackClient:
    def post(self, channel, text):
        if _SLACK_FAIL["on"]:
            raise RuntimeError("simulated Slack outage")
        _SLACK_SENT.append({"channel": channel, "text": text})


def build_fake_slack_client(integration):
    return _FakeSlackClient()


def reset_slack():
    _SLACK_SENT.clear()
    _SLACK_FAIL["on"] = False


def slack_sent() -> list[dict]:
    return list(_SLACK_SENT)


def set_slack_fail(on: bool):
    _SLACK_FAIL["on"] = on


# ── Jira fake ─────────────────────────────────────────────────────────────────

_JIRA_CANNED: dict[str, Decimal] = {}


class _FakeJiraClient:
    def fetch_issue_value(self, issue_key) -> Decimal:
        return Decimal(str(_JIRA_CANNED[issue_key]))


def build_fake_jira_client(integration):
    return _FakeJiraClient()


def set_jira_canned(mapping: dict):
    _JIRA_CANNED.clear()
    _JIRA_CANNED.update({k: Decimal(str(v)) for k, v in mapping.items()})
