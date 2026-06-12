"""
Analytics insights SEAM (Module 10 owns the LLM).

The DETERMINISTIC at-risk rollup is ALWAYS available (it is the
``risk_distribution`` in ``services.department_analytics`` — a pure count of
ON_TRACK / AT_RISK / CRITICAL over the cohort). This seam is for the Module-10
Fast-AI *anomaly narrative / highlight* on top of that deterministic rollup
(advisory, read-only) — until then production stays ``NotConfigured`` and nothing
is fabricated.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from django.utils.module_loading import import_string


class AnalyticsInsightsNotConfiguredError(RuntimeError):
    """Raised by :class:`NotConfiguredProvider` — the anomaly/insight narrative
    lands in Module 10. Callers treat this as a loud no-op, never fabricated text."""


class AnalyticsInsightsProvider(ABC):
    """The contract a Module-10 insights agent implements: given a deterministic
    department rollup, return an advisory narrative / anomaly highlight."""

    configured: bool = False

    @abstractmethod
    def summarize(self, *, rollup) -> dict:
        raise NotImplementedError


class NotConfiguredProvider(AnalyticsInsightsProvider):
    """Default: no agent wired. Every call raises (the deterministic rollup is the
    working baseline)."""

    configured = False

    def summarize(self, *, rollup) -> dict:
        raise AnalyticsInsightsNotConfiguredError(
            "No analytics insights agent is configured (it lands in Module 10). "
            "The deterministic at-risk rollup is the working baseline."
        )


def get_provider() -> AnalyticsInsightsProvider:
    from django.conf import settings

    dotted = getattr(
        settings, "ANALYTICS_INSIGHTS_PROVIDER", "apps.analytics.insights_agent.NotConfiguredProvider"
    )
    return import_string(dotted)()
