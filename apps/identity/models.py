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
    #: Optional human display name. NOT unique, nullable — existing rows default to
    #: NULL and the UI falls back to ``email`` (see the ``display`` property). Set via
    #: the Admin Hub; never required (keeps existing flows valid).
    display_name = models.CharField(max_length=255, null=True, blank=True, default=None)
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
    def display(self) -> str:
        """The effective display name: ``display_name`` when set, else ``email``.
        Always populated — UIs render this directly (no client-side fallback needed)."""
        return self.display_name or self.email

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


class SamlIdpConfig(TenantScopedModel):
    """Per-tenant SAML 2.0 IdP configuration for our Service Provider. One row per
    tenant (a tenant either has SSO/SAML configured or it doesn't).

    Stores only **public** IdP metadata — entity id, SSO URL, and the IdP's signing
    certificate (a public cert is not a secret) — plus the attribute names and the
    role map. Any SP-side *secret* (the SP private key, needed only when a tenant's
    IdP demands signed AuthnRequests / encrypted assertions) is referenced by env-var
    NAME via ``sp_private_key_secret_ref`` and resolved at runtime — never stored
    here and never committed (see DECISIONS D25, docs/SSO.md).
    """

    enabled = models.BooleanField(default=False)
    # ─ IdP (public) ─
    idp_entity_id = models.CharField(max_length=255)
    idp_sso_url = models.URLField(max_length=512)
    idp_x509_cert = models.TextField(
        help_text="IdP signing certificate (PEM body / base64). Public — used to "
        "verify assertion signatures."
    )
    # ─ Attribute → user/role mapping ─
    #: Assertion attribute carrying the user's email. Empty → fall back to NameID.
    email_attribute = models.CharField(max_length=128, blank=True, default="email")
    #: Assertion attribute carrying the IdP role/group.
    role_attribute = models.CharField(max_length=128, blank=True, default="role")
    #: Maps an IdP-asserted role/group value → our ``User.Role`` value. Tenant-owned
    #: policy; an unmapped/absent value falls back to the provisioned DB role.
    role_map = models.JSONField(default=dict, blank=True)
    # ─ Optional SP secret (referenced, never stored) ─
    #: Name of the env var holding the SP private-key PEM. NEVER the key itself.
    sp_private_key_secret_ref = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        db_table = "identity_saml_idp_config"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="uq_saml_config_tenant"),
        ]

    def __str__(self):
        return f"SAML config for tenant {self.tenant_id} ({'on' if self.enabled else 'off'})"


class DeviceSession(TenantScopedModel):
    """A login session/device (PHASE2 L1.3). Created at token issue; its id rides
    the JWTs as the ``did`` claim (which survives simplejwt refresh rotation, like
    the tenant/role claims). Revocation is enforced at REFRESH time — a revoked
    session cannot rotate, so it dies within the access-token lifetime (≤15 min).
    Additive: the token scheme itself is unchanged."""

    user = models.ForeignKey(
        "identity.User", on_delete=models.CASCADE, related_name="device_sessions"
    )
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")
    last_seen = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "identity_device_session"
        indexes = [models.Index(fields=["tenant", "user", "-last_seen"])]

    @property
    def active(self) -> bool:
        return self.revoked_at is None

    def __str__(self):
        return f"session {self.id} for {self.user_id} ({'active' if self.active else 'revoked'})"


class LoginEvent(TenantScopedModel):
    """Login history (PHASE2 L1.3) — success/failure/lockout/logout/revocation per
    attempt, with best-effort ip/user-agent. ``user`` is null for failed attempts
    against unknown emails (the attempted email is still recorded, tenant-scoped)."""

    class Event(models.TextChoices):
        LOGIN_OK = "LOGIN_OK", "Login succeeded"
        LOGIN_FAILED = "LOGIN_FAILED", "Login failed"
        LOCKOUT = "LOCKOUT", "Locked out (too many attempts)"
        MFA_FAILED = "MFA_FAILED", "MFA code rejected"
        LOGOUT = "LOGOUT", "Logged out"
        SESSION_REVOKED = "SESSION_REVOKED", "Session revoked"
        PASSWORD_CHANGED = "PASSWORD_CHANGED", "Password changed"

    user = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="login_events",
    )
    email = models.EmailField()
    event = models.CharField(max_length=20, choices=Event.choices)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")

    class Meta:
        db_table = "identity_login_event"
        indexes = [models.Index(fields=["tenant", "user", "-created_at"])]

    def __str__(self):
        return f"{self.event} {self.email} @ {self.created_at}"
