from django.apps import AppConfig


class TestSupportConfig(AppConfig):
    """Installed ONLY under config.settings.test. Provides concrete fixtures
    (e.g. a concrete TenantScopedModel) that never ship to dev/prod."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.testsupport"
    label = "testsupport"
