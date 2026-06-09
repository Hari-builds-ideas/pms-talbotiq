from django.db import models

from apps.tenancy.models import TenantScopedModel


class ScopedThing(TenantScopedModel):
    """A minimal concrete TenantScopedModel so tenancy isolation can be tested
    without depending on any real domain model. Its table is created via
    run-syncdb during test-DB setup (the app has no migrations and is not in
    dev/prod INSTALLED_APPS)."""

    name = models.CharField(max_length=100)

    class Meta:
        db_table = "testsupport_scopedthing"
