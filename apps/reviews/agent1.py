"""
Agent-1 (Review Assistant) SEAM — interface only.

This module defines the contract for producing an AI review draft, but it
contains NO LLM, NO LangGraph, and NO real agent. The concrete agent lands in
Module 10 and is swapped in via the ``REVIEW_ASSISTANT_PROVIDER`` setting — no
code change here. Same shape as the Module-2 Jira seam (``apps/goals/jira.py``).

Until then the default provider is :class:`NotConfiguredProvider`, which raises
loudly on use. The Celery task (``apps/reviews/tasks.py``) therefore logs a
clear warning and skips cleanly — the review stays in DRAFT and the manual path
is never blocked. Everything a configured provider returns is locked
PENDING_HUMAN_REVIEW through the state machine; an AI draft can never be
published directly.
"""
import abc

from django.conf import settings
from django.utils.module_loading import import_string


class ReviewAssistantNotConfiguredError(Exception):
    """Raised when an AI draft is requested but no concrete Agent-1 provider exists."""


class ReviewAssistantProvider(abc.ABC):
    """Interface for drafting one review with Agent 1 (the Review Assistant).

    The CONCRETE agent is Module 10. This MVP ships only the abstract contract
    plus :class:`NotConfiguredProvider` as the default.

    Module 10's concrete provider implements the shared Large-AI safeguard
    pipeline (Doc 3 §5):

    1. Gather tenant-scoped evidence for the review's subject — Module-2 Goals,
       KPIs and CycleScores, plus (later) Module-4 360° Feedback.
    2. PII-scrub the evidence BEFORE any model call.
    3. Run the Agent-1 LangGraph graph through the ``LLMGateway`` (never a
       direct SDK call), traced in LangSmith.
    4. Structure the output as a draft with a confidence score and citations
       back to the evidence used.

    Its API surface is gated in Module 10 with
    ``apps.billing.gate.requires_entitlement("agent1")`` (FULL_AI pack), and the
    result is always LOCKED PENDING_HUMAN_REVIEW via
    ``state_machine.ai_draft_ready`` — the HITL gate; an AI draft is never
    published directly.
    """

    # Concrete, working providers set this True so callers can detect a real one.
    configured = True

    @abc.abstractmethod
    def draft(self, review) -> dict:
        """Return the AI draft for ``review`` as a dict::

            {
                "draft_body": str,
                "confidence_score": Decimal | None,
                "citations": list | None,
            }
        """
        raise NotImplementedError


class NotConfiguredProvider(ReviewAssistantProvider):
    """Default provider for the MVP: there is no agent yet, so any draft raises
    :class:`ReviewAssistantNotConfiguredError`. The ``configured`` marker lets
    callers detect this without catching the exception."""

    configured = False

    def draft(self, review) -> dict:
        raise ReviewAssistantNotConfiguredError(
            "No Review Assistant provider configured; Agent 1 lands in Module 10."
        )


def get_provider() -> ReviewAssistantProvider:
    """Return the configured :class:`ReviewAssistantProvider`.

    Resolves the ``REVIEW_ASSISTANT_PROVIDER`` setting (an import string) when
    present, so Module 10 can swap in the real agent via config alone. For the
    MVP no setting is configured, so this returns a :class:`NotConfiguredProvider`.
    """
    dotted = getattr(settings, "REVIEW_ASSISTANT_PROVIDER", None)
    if dotted:
        return import_string(dotted)()
    return NotConfiguredProvider()
