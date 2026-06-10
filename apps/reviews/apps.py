from django.apps import AppConfig


class ReviewsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reviews"

    def ready(self):
        """Register "review" as an approval-route artifact type (Module 5).

        Done in ready() so all apps' models are loaded; the import is deferred to
        here to avoid touching the app registry at module-import time.
        """
        from .approval_integration import register

        register()
