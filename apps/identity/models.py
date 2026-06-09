"""
Custom tenant-scoped User.

The user is a ``TenantScopedModel`` (UUID pk, tenant FK, soft delete, scoped
default manager) combined with Django's ``AbstractBaseUser`` (password handling)
and ``PermissionsMixin``. Email is unique **per tenant** (not globally), enforced
by a UniqueConstraint — which is why ``auth.E003`` is intentionally silenced.
"""
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models

from apps.tenancy.managers import TenantScopedManager
from apps.tenancy.models import TenantScopedModel


class UserManager(TenantScopedManager, BaseUserManager):
    """Tenant-scoped reads (from TenantScopedManager) + password-aware creation
    helpers (from BaseUserManager)."""

    use_in_migrations = False

    def create_user(self, email, password=None, *, tenant=None, role=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address.")
        if tenant is None:
            raise ValueError("Users must belong to a tenant.")
        email = self.normalize_email(email)
        if role is None:
            role = User.Role.EMPLOYEE
        user = self.model(email=email, tenant=tenant, role=role, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, *, tenant=None, **extra_fields):
        if tenant is None:
            raise ValueError("Superusers must belong to a tenant.")
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True or extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_staff=True and is_superuser=True.")
        return self.create_user(email, password=password, tenant=tenant, **extra_fields)

    def get_by_natural_id_unscoped(self, pk):
        """Bootstrap-only principal lookup by globally-unique UUID pk, used before
        a tenant is bound (session / SSO complete). A pk identifies exactly one
        user in one tenant, so this cannot leak cross-tenant data. It is a single
        get(), never a filter/list API."""
        return models.QuerySet(self.model, using=self._db).get(
            pk=pk, deleted_at__isnull=True
        )


class User(AbstractBaseUser, PermissionsMixin, TenantScopedModel):
    class Role(models.TextChoices):
        EMPLOYEE = "EMPLOYEE", "Employee"
        MANAGER = "MANAGER", "Manager"
        HRBP = "HRBP", "HRBP"
        ADMIN = "ADMIN", "Admin"

    email = models.EmailField()
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.EMPLOYEE)
    # Reporting line / org tree.
    manager = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reports",
        limit_choices_to={"deleted_at__isnull": True},
    )
    mfa_enabled = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()
    all_objects = UserManager(include_deleted=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "identity_user"
        ordering = ["email"]
        constraints = [
            # Email is unique per tenant (not globally).
            models.UniqueConstraint(fields=["tenant", "email"], name="uq_user_tenant_email"),
        ]
        indexes = [models.Index(fields=["tenant", "email"], name="ix_user_tenant_email")]

    def __str__(self):
        return f"{self.email} [{self.role}]"

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_hrbp(self):
        return self.role == self.Role.HRBP

    @property
    def is_manager(self):
        return self.role == self.Role.MANAGER

    @property
    def is_employee(self):
        return self.role == self.Role.EMPLOYEE
