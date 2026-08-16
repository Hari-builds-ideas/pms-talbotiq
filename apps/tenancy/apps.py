from django.apps import AppConfig


class TenancyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tenancy"

    def ready(self):
        # Registers the cache-invalidation receivers that make a tenant
        # suspension take effect on the next request (C3, see signals.py).
        from . import signals  # noqa: F401
