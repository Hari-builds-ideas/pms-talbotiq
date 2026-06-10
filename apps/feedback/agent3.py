"""
Agent-3 (Feedback Summarization) SEAM — interface only.

This module defines the contract for summarising a closed 360° cycle, but it
contains NO LLM, NO LangGraph, and NO real agent. The concrete agent lands in
Module 10 and is swapped in via the ``FEEDBACK_SUMMARIZER_PROVIDER`` setting —
no code change here. Same shape as the Module-3 Agent-1 seam
(``apps/reviews/agent1.py``).

Until then the default provider is :class:`NotConfiguredProvider`, which raises
loudly on use. The Celery task (``apps/feedback/tasks.py``) therefore logs a
clear warning and skips cleanly — the deterministic pipeline (anonymise ->
threshold -> breach guard -> summary record) still runs in full; only the 4
theme sections stay NULL, never fabricated. Everything a configured provider
returns is locked behind the summary gates (PENDING_HUMAN_REVIEW / HRBP_HOLD);
an AI summary can never be released directly.
"""
import abc

from django.conf import settings
from django.utils.module_loading import import_string


class FeedbackSummarizerNotConfiguredError(Exception):
    """Raised when a summary is requested but no concrete Agent-3 provider exists."""


class FeedbackSummarizerProvider(abc.ABC):
    """Interface for summarising one 360° cycle with Agent 3 (Feedback Summarization).

    The CONCRETE agent is Module 10. This MVP ships only the abstract contract
    plus :class:`NotConfiguredProvider` as the default.

    Module 10's concrete provider implements the shared Large-AI safeguard
    pipeline (Doc 3 §5) per the Agent-3 diagram:

    1. Consume ONLY the anonymised payload from
       :func:`apps.feedback.anonymize.build_anonymized_payload` — NEVER the raw
       Feedback rows; the deterministic pre-LLM breach guard has already run.
    2. PII-scrub the payload BEFORE any model call.
    3. Run the Agent-3 LangGraph graph through the ``LLMGateway`` (never a
       direct SDK call), traced in LangSmith.
    4. Structure the output as the 4 theme sections plus a confidence score.
    5. Run a POST-LLM anonymity-breach check on its own output — the model must
       not reintroduce identity the deterministic guard stripped.

    Its API surface is gated in Module 10 with
    ``apps.billing.gate.requires_entitlement("agent3")`` (FULL_AI pack), and the
    result is always locked through the same summary gates
    (PENDING_HUMAN_REVIEW, or HRBP_HOLD when held) — the HITL gate; an AI
    summary is never released directly.
    """

    # Concrete, working providers set this True so callers can detect a real one.
    configured = True

    @abc.abstractmethod
    def summarize(self, payload) -> dict:
        """Return the AI summary for the anonymised ``payload`` as a dict::

            {
                "sections": {
                    "strengths": str,
                    "growth": str,
                    "themes": str,
                    "risks": str,
                },
                "confidence_score": Decimal | None,
            }
        """
        raise NotImplementedError


class NotConfiguredProvider(FeedbackSummarizerProvider):
    """Default provider for the MVP: there is no agent yet, so any summarize
    raises :class:`FeedbackSummarizerNotConfiguredError`. The ``configured``
    marker lets callers detect this without catching the exception."""

    configured = False

    def summarize(self, payload) -> dict:
        raise FeedbackSummarizerNotConfiguredError(
            "No Feedback Summarizer provider configured; Agent 3 lands in Module 10."
        )


def get_provider() -> FeedbackSummarizerProvider:
    """Return the configured :class:`FeedbackSummarizerProvider`.

    Resolves the ``FEEDBACK_SUMMARIZER_PROVIDER`` setting (an import string)
    when present, so Module 10 can swap in the real agent via config alone. For
    the MVP no setting is configured, so this returns a
    :class:`NotConfiguredProvider`.
    """
    dotted = getattr(settings, "FEEDBACK_SUMMARIZER_PROVIDER", None)
    if dotted:
        return import_string(dotted)()
    return NotConfiguredProvider()
