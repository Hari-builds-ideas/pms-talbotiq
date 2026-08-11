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

        from .health import CeleryBrokerHealthCheck, ReplicaDatabaseHealthCheck

        plugin_dir.register(CeleryBrokerHealthCheck)
        plugin_dir.register(ReplicaDatabaseHealthCheck)

        # Deploy-time configuration checks. Importing the module is what registers
        # them; they run only under `manage.py check --deploy`.
        from . import checks  # noqa: F401
