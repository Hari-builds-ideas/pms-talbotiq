from django.apps import AppConfig


class AiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ai"
    verbose_name = "AI Agents (LLM Gateway + LangGraph)"

    def ready(self):
        # Agent 2 (KPI Intelligence) subscribes to the Module-2 recompute signal to
        # surface nudges (best-effort; never mutates scoring). Also weekly-beat
        # callable via apps.ai.agents.kpi.run_kpi_nudges.
        from apps.goals.signals import cycle_scores_recomputed

        from .agents.kpi import on_cycle_scores_recomputed

        cycle_scores_recomputed.connect(
            on_cycle_scores_recomputed, dispatch_uid="agent2_kpi_nudges"
        )
        # Import the agent modules so their FakeLLMProvider output builders register
        # (the seam providers are pointed at these via settings at go-live).
        from .agents import career, feedback, jd, review, succession  # noqa: F401
