"""
Career Roadmap agent SEAM (Module 10 owns the LLM).

A loud, honest seam — identical in shape to the Module-3 Agent-1, Module-6 JD
generator, and Module-8 Agent-4 seams: an ABC + a ``NotConfiguredProvider`` that
raises a typed error + a ``get_provider()`` resolving a settings import-string.
Until Module 10 ships a provider, production stays NotConfigured: the AI-enriched
roadmap surfaces a 503 and the DETERMINISTIC roadmap (the working baseline) is
left completely intact. Nothing is ever fabricated.

Tests exercise the full enrichment pipeline through a deterministic in-repo fake
provider (see ``settings.CAREER_ROADMAP_PROVIDER``); no network call ever runs.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from django.utils.module_loading import import_string


class CareerRoadmapNotConfiguredError(RuntimeError):
    """Raised by :class:`NotConfiguredProvider` to signal that no real Career
    Roadmap agent is wired — Agent lands in Module 10. Callers treat this as a
    loud no-op (503), never as an opportunity to fabricate a roadmap."""


class CareerRoadmapProvider(ABC):
    """The contract a real Career Roadmap agent (Module 10) implements.

    Given the employee's deterministic gap + the deterministic baseline tiers, it
    drafts an enriched, still-ADVISORY tiered path (never auto-promotion). It must
    return ``{"tiers": [...], "confidence_score": Decimal|float}``.
    """

    #: Subclasses set True so callers can cheaply check ``provider.configured``.
    configured: bool = False

    @abstractmethod
    def draft(self, *, employee_id, target_label, gap, baseline_tiers) -> dict:
        """Return an enriched advisory roadmap payload."""
        raise NotImplementedError


class NotConfiguredProvider(CareerRoadmapProvider):
    """The default provider: no agent wired. Every call raises so the task layer
    logs-and-skips and the endpoint returns a loud 503."""

    configured = False

    def draft(self, *, employee_id, target_label, gap, baseline_tiers) -> dict:
        raise CareerRoadmapNotConfiguredError(
            "No Career Roadmap agent is configured (it lands in Module 10). The "
            "deterministic roadmap is the working baseline."
        )


def get_provider() -> CareerRoadmapProvider:
    """Resolve the configured Career Roadmap provider from
    ``settings.CAREER_ROADMAP_PROVIDER`` (an import string). Defaults to
    :class:`NotConfiguredProvider` when unset."""
    from django.conf import settings

    dotted = getattr(
        settings, "CAREER_ROADMAP_PROVIDER", "apps.career.roadmap_agent.NotConfiguredProvider"
    )
    provider_cls = import_string(dotted)
    return provider_cls()
