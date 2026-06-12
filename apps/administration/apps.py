from django.apps import AppConfig


class AdministrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.administration"
    # Explicit label (NOT "admin" — that is django.contrib.admin's reserved label).
    label = "administration"
    verbose_name = "Administration (Admin Hub)"
