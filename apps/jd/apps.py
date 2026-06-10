from django.apps import AppConfig


class JdConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.jd"

    def ready(self):
        """Register "jd" as an approval-route artifact type (Module 5 consumer #2).

        Done in ready() so all models are loaded; the import is deferred to here
        to avoid touching the app registry at module-import time. Proves the
        Module-5 engine is generic — a JD has no employee subject, so a MANAGER
        approval step is correctly unresolvable (the engine's 422).
        """
        from .approval_integration import register

        register()
