from django.contrib.auth.backends import ModelBackend

from .models import User


class TenantModelBackend(ModelBackend):
    """Resolves the session principal by its globally-unique pk before a tenant
    is bound. The scoped default manager fails closed without tenant context, so
    a plain ModelBackend would never find the session user on the SSO path."""

    def get_user(self, user_id):
        try:
            user = User.objects.get_by_natural_id_unscoped(user_id)
        except User.DoesNotExist:
            return None
        return user if self.user_can_authenticate(user) else None
