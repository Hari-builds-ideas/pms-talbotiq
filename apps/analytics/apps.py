from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.analytics"
    verbose_name = "Analytics & Reporting"

    def ready(self):
        # Invalidate the per-tenant analytics cache whenever cycle scores are
        # recomputed (Module 2), so department rollups never serve stale numbers.
        from apps.goals.signals import cycle_scores_recomputed

        from .services import _on_cycle_scores_recomputed

        cycle_scores_recomputed.connect(
            _on_cycle_scores_recomputed,
            dispatch_uid="analytics_invalidate_on_recompute",
        )
