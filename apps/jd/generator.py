"""
JD Generator SEAM — interface only.

This module defines the contract for AI-generating a job-description body, but it
contains NO LLM, NO LangGraph, and NO real generator. The concrete generator
lands in Module 10 and is swapped in via the ``JD_GENERATOR_PROVIDER`` setting —
no code change here. Same shape as the Module-3 Review-Assistant seam
(``apps/reviews/agent1.py``) and the Module-2 Jira seam (``apps/goals/jira.py``).

Until then the default provider is :class:`NotConfiguredProvider`, which raises
loudly on use. The Celery task (``apps/jd/tasks.py``) therefore validates the
inputs, then logs a clear warning and skips cleanly — the JD is never touched
and NO fake body is ever written. Everything a configured provider returns is
locked PENDING_HUMAN_REVIEW through the lifecycle; a generated JD can never be
published directly.
"""
import abc

from django.conf import settings
from django.utils.module_loading import import_string


class JDGeneratorNotConfiguredError(Exception):
    """Raised when generation is requested but no concrete provider exists."""


class JDGeneratorProvider(abc.ABC):
    """Interface for generating one JD body from structured role inputs.

    The CONCRETE generator is Module 10. This MVP ships only the abstract
    contract plus :class:`NotConfiguredProvider` as the default.

    Module 10's concrete provider implements the shared Large-AI safeguard
    pipeline (Doc 3 §5):

    1. Take the role inputs (title, level, department, the inputs snapshot) for
       the JD.
    2. Run the JD-Generator LangGraph graph through the ``LLMGateway`` (never a
       direct SDK call), traced in LangSmith.
    3. Structure the output as a body ``{summary, responsibilities, must_haves,
       nice_to_haves}`` with a confidence score and citations.

    Its API surface is gated in Module 10 with the JD-generator entitlement, and
    the result is always LOCKED PENDING_HUMAN_REVIEW via the lifecycle — the HITL
    gate; a generated JD is never published directly.
    """

    # Concrete, working providers set this True so callers can detect a real one.
    configured = True

    @abc.abstractmethod
    def generate(self, *, jd, inputs) -> dict:
        """Return the generated body for ``jd`` as a dict::

            {
                "body": {"summary": str, "responsibilities": [str],
                         "must_haves": [str], "nice_to_haves": [str]},
                "confidence_score": Decimal | None,
                "citations": list | None,
            }
        """
        raise NotImplementedError


class NotConfiguredProvider(JDGeneratorProvider):
    """Default provider for the MVP: there is no generator yet, so any call
    raises :class:`JDGeneratorNotConfiguredError`. The ``configured`` marker lets
    callers detect this without catching the exception."""

    configured = False

    def generate(self, *, jd, inputs) -> dict:
        raise JDGeneratorNotConfiguredError(
            "No JD Generator provider configured; the generator lands in Module 10."
        )


def get_provider() -> JDGeneratorProvider:
    """Return the configured :class:`JDGeneratorProvider`.

    Resolves the ``JD_GENERATOR_PROVIDER`` setting (an import string) so Module 10
    can swap in the real generator via config alone. For the MVP the setting
    points at :class:`NotConfiguredProvider`.
    """
    dotted = getattr(settings, "JD_GENERATOR_PROVIDER", None)
    if dotted:
        return import_string(dotted)()
    return NotConfiguredProvider()
