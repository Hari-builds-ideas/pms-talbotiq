"""
Administration services — the Admin-only, audited tenant/user/role mutators.

Admin scope is the whole tenant (Admin = TENANT data scope), so there is no
per-row scope check beyond tenant isolation: the views resolve a referenced user
through the tenant-scoped ``User.objects`` manager, so a cross-tenant id is a 404
before a service is ever called, and every write is additionally bound to the
actor's tenant. Every consequential action writes an immutable audit row BEFORE it
takes effect.

The reporting line is NOT re-implemented here — it delegates to the Module-7
``apps.org.reassign.reassign_reporting_line`` (with its cycle check + cache
invalidation), per the contract's "reuse, don't fork".
"""
from __future__ import annotations

from apps.audit.services import record
from apps.identity.models import User
from apps.org.reassign import reassign_reporting_line as _org_reassign
from apps.tenancy.context import tenant_context

from .exceptions import InvalidAdminInput
from .models import TenantConfig

_VALID_ROLES = set(User.Role.values)


# ── user / role management ─────────────────────────────────────────────────────


def create_user(actor, *, email, role, manager=None, password=None, mfa_enabled=False) -> User:
    """Create a user in the actor's tenant with ``role`` (Admin-only at the view).
    Audited before the create. 422 on an unknown role or an email already in use in
    the tenant."""
    if role not in _VALID_ROLES:
        raise InvalidAdminInput(f"Unknown role '{role}'.", code="UNKNOWN_ROLE")
    tid = actor.tenant_id
    with tenant_context(tid):
        # all_objects so a soft-deleted user still reserving the email is caught.
        if User.all_objects.filter(email=email).exists():
            raise InvalidAdminInput(
                f"Email '{email}' is already in use in this tenant.", code="EMAIL_TAKEN"
            )
        record(
            action="admin.user_created",
            actor=actor,
            target_type="user",
            target_id="",
            metadata={"email": email, "role": role,
                      "manager": str(manager.id) if manager else None},
            tenant=tid,
        )
        return User.objects.create_user(
            email=email,
            password=password,
            tenant=actor.tenant,
            role=role,
            manager=manager,
            mfa_enabled=mfa_enabled,
        )


def set_role(actor, user, role) -> User:
    """Assign ``role`` to ``user`` (Admin-only). Audited before the change."""
    if role not in _VALID_ROLES:
        raise InvalidAdminInput(f"Unknown role '{role}'.", code="UNKNOWN_ROLE")
    with tenant_context(user.tenant_id):
        record(
            action="admin.role_assigned",
            actor=actor,
            target_type="user",
            target_id=user.id,
            metadata={"previous_role": user.role, "new_role": role},
            tenant=user.tenant_id,
        )
        user.role = role
        user.save(update_fields=["role", "updated_at"])
        return user


def set_active(actor, user, *, is_active: bool) -> User:
    """Activate/deactivate ``user`` (Admin-only). Audited before the change. A
    deactivated user is excluded from the org tree + rollups (Module 7) and cannot
    authenticate."""
    action = "admin.user_reactivated" if is_active else "admin.user_deactivated"
    with tenant_context(user.tenant_id):
        record(
            action=action,
            actor=actor,
            target_type="user",
            target_id=user.id,
            metadata={"is_active": is_active},
            tenant=user.tenant_id,
        )
        user.is_active = is_active
        user.save(update_fields=["is_active", "updated_at"])
        return user


def set_reporting_line(actor, user, new_manager) -> User:
    """Reassign ``user``'s manager — delegates to the Module-7 cycle-checked
    ``reassign_reporting_line`` (which audits + invalidates the org cache). Reused,
    never duplicated."""
    return _org_reassign(actor, user, new_manager)


def list_users(actor) -> list[User]:
    """Every user in the actor's tenant (Admin-only). Tenant-scoped by the manager."""
    with tenant_context(actor.tenant_id):
        return list(User.objects.all().order_by("email"))


# ── tenant config ──────────────────────────────────────────────────────────────


def get_tenant_config(actor) -> TenantConfig:
    """The tenant's config row, creating an empty one on first access."""
    tid = actor.tenant_id
    with tenant_context(tid):
        config = TenantConfig.objects.filter(tenant_id=tid).first()
        if config is None:
            config = TenantConfig(tenant_id=tid, settings={})
            config.save()
        return config


def update_tenant_config(actor, *, settings) -> TenantConfig:
    """Replace the tenant's ``settings`` bag (Admin-only). Audited before the change.
    ``settings`` must be a JSON object (dict)."""
    if not isinstance(settings, dict):
        raise InvalidAdminInput("settings must be a JSON object.", code="SETTINGS_NOT_OBJECT")
    tid = actor.tenant_id
    config = get_tenant_config(actor)
    with tenant_context(tid):
        record(
            action="admin.tenant_config_updated",
            actor=actor,
            target_type="tenant",
            target_id=tid,
            metadata={"keys": sorted(settings.keys())},
            tenant=tid,
        )
        config.settings = settings
        config.save(update_fields=["settings", "updated_at"])
        return config
