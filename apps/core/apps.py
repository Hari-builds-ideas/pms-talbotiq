from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"

    def ready(self):
        """Register custom health-check plugins once the app registry is ready.

        Imports are done inside ``ready()`` (not at module top) to avoid
        touching the app registry before Django has finished loading apps.
        """
        from health_check.plugins import plugin_dir

        from .health import CeleryBrokerHealthCheck

        plugin_dir.register(CeleryBrokerHealthCheck)
