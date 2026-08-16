"""
Keep the cached tenant status honest (C3).

``tenant_is_active`` is consulted on every authenticated request, so it reads
from cache. This signal is what makes a suspension take effect on the NEXT
request rather than whenever the TTL happens to expire — without it, "we
suspended them" and "they stopped being served" are up to five minutes apart, and
the whole point of C3 is closing that gap.

Fires on every ``Tenant`` save rather than only when ``status`` changed: the
check is one cache delete, tenant rows are written rarely, and a conditional
would need the previous value, which is exactly the kind of cleverness that
silently stops firing after an unrelated refactor.
"""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Tenant
from .status import forget_tenant_status


@receiver(post_save, sender=Tenant, dispatch_uid="tenancy_status_invalidate_save")
def _invalidate_on_save(sender, instance, **kwargs):
    forget_tenant_status(instance.id)


@receiver(post_delete, sender=Tenant, dispatch_uid="tenancy_status_invalidate_delete")
def _invalidate_on_delete(sender, instance, **kwargs):
    forget_tenant_status(instance.id)
