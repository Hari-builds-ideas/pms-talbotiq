"""
LangSmith tracing — a no-op behind config. When ``LANGSMITH_API_KEY`` is unset (the
default, and always tonight) ``trace()`` is a do-nothing context manager, so the
gateway/agents run identically with or without tracing wired. When a key is set
AND the ``langsmith`` package is installed (production), swap the body of
``_start_trace`` for a real LangSmith run — the call sites do not change.
"""
from __future__ import annotations

import contextlib

from django.conf import settings


def tracing_enabled() -> bool:
    return bool(getattr(settings, "LANGSMITH_API_KEY", "") or "")


@contextlib.contextmanager
def trace(name, **metadata):
    """Trace a span. No-op unless LangSmith is configured (it is not tonight)."""
    if not tracing_enabled():
        yield None
        return
    # Production seam: start a LangSmith run here (the package + key land with the
    # provider — see NEEDS_HARI_llm_provider.md). Kept a no-op until then.
    yield None
