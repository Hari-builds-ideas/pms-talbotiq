"""
Shared factory_boy factories. Importable from any app's tests:

    from apps.testsupport.factories import TenantFactory, UserFactory

Model references are lazy strings so importing this module never requires the
app registry to be ready. ``UserFactory`` routes through the custom
``create_user`` manager so passwords are Argon2-hashed exactly as in production.
"""
import factory
from factory.django import DjangoModelFactory


class TenantFactory(DjangoModelFactory):
    class Meta:
        model = "tenancy.Tenant"

    name = factory.Sequence(lambda n: f"Tenant {n}")
    slug = factory.Sequence(lambda n: f"tenant-{n}")
    status = "ACTIVE"


class UserFactory(DjangoModelFactory):
    class Meta:
        model = "identity.User"

    tenant = factory.SubFactory(TenantFactory)
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    role = "EMPLOYEE"
    is_active = True
    mfa_enabled = False
    password = "pass12345!"

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop("password", None)
        manager = model_class._default_manager
        return manager.create_user(*args, password=password, **kwargs)


class ScopedThingFactory(DjangoModelFactory):
    class Meta:
        model = "testsupport.ScopedThing"

    # tenant is intentionally NOT a SubFactory: callers pass it explicitly so
    # cross-tenant tests stay unambiguous about which tenant owns each row.
    name = factory.Sequence(lambda n: f"thing-{n}")
