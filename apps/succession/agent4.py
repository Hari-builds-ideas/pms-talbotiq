"""
Agent-4 (Successor Planning) ENRICHMENT SEAM — interface only.

This module defines the contract for ENRICHING a deterministic succession plan
with Agent 4, but it contains NO LLM, NO LangGraph, and NO real agent. The
concrete agent lands in Module 10 and is swapped in via the
``SUCCESSION_ANALYZER_PROVIDER`` setting — no code change here. Same loud-seam
shape as the Module-3 Review-Assistant and Module-6 JD-Generator seams.

THE KEY DIFFERENCE from those seams: here the baseline is CORE, not faked. The
deterministic engine already produced a real, published-quality plan; Agent 4
only enriches it (richer readiness using anonymised 360 themes, narrative,
sharper red-flags) into a NEW plan (source=AI) locked PENDING_HUMAN_REVIEW with a
confidence score, for the HRBP to re-review. Until the provider is configured the
enrich task logs-and-skips and the deterministic plan stays intact and valid.

Module 10's concrete provider implements the shared Large-AI safeguard pipeline
(Doc 3 §5): validate input schema (scoring weights sum to 1.0 -> else
INVALID_INPUT_SCHEMA, zero tokens), gather tenant-scoped INTERNAL evidence
(CycleScores, goals, ANONYMISED Module-4 360 — never raw givers), PII-scrub,
run the LangGraph graph through the LLMGateway, structure + score the output, and
lock it PENDING_HUMAN_REVIEW. Its surface is gated with
``requires_entitlement("agent4")``.
"""
import abc

from django.conf import settings
from django.utils.module_loading import import_string


class SuccessionAnalyzerNotConfiguredError(Exception):
    """Raised when enrichment is requested but no concrete Agent-4 provider exists."""


class SuccessionAnalyzerProvider(abc.ABC):
    """Interface for enriching a deterministic plan with Agent 4.

    The CONCRETE agent is Module 10. This MVP ships only the abstract contract +
    :class:`NotConfiguredProvider` as the default.
    """

    # Concrete, working providers set this True so callers can detect a real one.
    configured = True

    @abc.abstractmethod
    def analyze(self, *, critical_role, plan) -> dict:
        """Return the enriched analysis for ``critical_role`` (building on the
        deterministic ``plan``) as a dict::

            {
                "ranked_bench": [...],
                "coverage_status": "RED" | "AMBER" | "GREEN",
                "red_flags": [...],
                "confidence_score": Decimal | None,
            }
        """
        raise NotImplementedError


class NotConfiguredProvider(SuccessionAnalyzerProvider):
    """Default provider for the MVP: there is no agent yet, so any call raises
    :class:`SuccessionAnalyzerNotConfiguredError`. The ``configured`` marker lets
    callers detect this without catching the exception."""

    configured = False

    def analyze(self, *, critical_role, plan) -> dict:
        raise SuccessionAnalyzerNotConfiguredError(
            "No Succession Analyzer provider configured; Agent 4 lands in Module 10."
        )


def get_provider() -> SuccessionAnalyzerProvider:
    """Return the configured :class:`SuccessionAnalyzerProvider`.

    Resolves the ``SUCCESSION_ANALYZER_PROVIDER`` setting (an import string) so
    Module 10 can swap in the real agent via config alone. For the MVP the setting
    points at :class:`NotConfiguredProvider`.
    """
    dotted = getattr(settings, "SUCCESSION_ANALYZER_PROVIDER", None)
    if dotted:
        return import_string(dotted)()
    return NotConfiguredProvider()
