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


def create_user(
    actor, *, email, role, manager=None, password=None, mfa_enabled=False, display_name=None
) -> User:
    """Create a user in the actor's tenant with ``role`` (Admin-only at the view).
    Audited before the create. 422 on an unknown role or an email already in use in
    the tenant. ``display_name`` is optional (empty → email fallback)."""
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
            display_name=(display_name or None),
        )


# Role ordering for the import privilege-escalation ceiling (mirrors the invite
# and SAML rank caps): an importer may create/assign a role AT OR BELOW their own,
# never above it — so an HRBP import can't mint ADMINs.
_ROLE_RANK = {
    User.Role.EMPLOYEE: 0,
    User.Role.MANAGER: 1,
    User.Role.HRBP: 2,
    User.Role.ADMIN: 3,
}


def bulk_import_employees(actor, rows: list[dict]) -> dict:
    """Bulk-onboard employees from parsed CSV rows into the actor's tenant.

    Each row: ``{name, email, role, department, designation, manager}`` (manager =
    the manager's EMAIL). Behaviour:
      * **Idempotent upsert by email** — an existing tenant user is UPDATED (role/
        department/title/name), a new email is CREATED (with an UNUSABLE password:
        imported users sign in via Google/SSO, or set a password via "forgot
        password" — no plaintext password is ever transmitted or stored).
      * **Per-row validation** — a bad row is reported in ``errors`` and skipped;
        one bad row never aborts the whole import.
      * **Seat enforcement** — a CREATE that would exceed the tenant's seats is a
        row error (server-side seat limit, never bypassed). Updates don't add seats.
      * **Role ceiling** — a row role above the importer's own rank is refused.
      * **Reporting lines** — resolved in a second pass by manager email, so a
        manager listed later in the file still links (with the org cycle guard).

    Returns ``{created, updated, skipped, total, errors:[{row,email,error}]}``.
    Fully tenant-scoped; a manager email that isn't in this tenant is a row error,
    never a cross-tenant link.
    """
    from apps.billing.services import can_add_user

    actor_rank = _ROLE_RANK.get(actor.role, 0)
    created = updated = 0
    errors: list[dict] = []
    # email(lower) → (user, manager_email or None) for the second (reporting) pass.
    linkables: dict[str, tuple] = {}

    with tenant_context(actor.tenant_id):
        # ── Pass 1: validate + upsert people ──────────────────────────────────
        for idx, raw in enumerate(rows, start=1):
            email = User.objects.normalize_email(str(raw.get("email", "")).strip())
            name = str(raw.get("name", "")).strip()
            role = str(raw.get("role", "") or User.Role.EMPLOYEE).strip().upper()
            department = str(raw.get("department", "")).strip()
            designation = str(raw.get("designation", "")).strip()
            manager_email = str(raw.get("manager", "")).strip().lower()

            if not email or "@" not in email:
                errors.append({"row": idx, "email": email, "error": "Missing or invalid email."})
                continue
            if role not in _VALID_ROLES:
                errors.append({"row": idx, "email": email, "error": f"Unknown role '{role}'."})
                continue
            if _ROLE_RANK.get(role, 0) > actor_rank:
                errors.append({"row": idx, "email": email,
                               "error": "You can't import a user at a higher role than your own."})
                continue

            existing = User.all_objects.filter(email=email).first()
            try:
                if existing is None:
                    ok, reason = can_add_user(actor.tenant_id)
                    if not ok:
                        errors.append({"row": idx, "email": email, "error": reason})
                        continue
                    record(
                        action="admin.user_imported", actor=actor, target_type="user",
                        target_id="", metadata={"email": email, "role": role},
                        tenant=actor.tenant_id,
                    )
                    user = User.objects.create_user(
                        email=email, password=None, tenant=actor.tenant, role=role,
                        display_name=(name or None), department=department, title=designation,
                    )
                    created += 1
                else:
                    fields = []
                    if name and existing.display_name != name:
                        existing.display_name = name; fields.append("display_name")
                    if existing.role != role:
                        existing.role = role; fields.append("role")
                    if department and existing.department != department:
                        existing.department = department; fields.append("department")
                    if designation and existing.title != designation:
                        existing.title = designation; fields.append("title")
                    if fields:
                        record(
                            action="admin.user_import_updated", actor=actor,
                            target_type="user", target_id=existing.id,
                            metadata={"fields": sorted(fields)}, tenant=actor.tenant_id,
                        )
                        existing.save(update_fields=[*fields, "updated_at"])
                    user = existing
                    updated += 1
            except Exception as exc:  # noqa: BLE001 — isolate a bad row, keep going
                errors.append({"row": idx, "email": email, "error": f"Could not save: {exc}"})
                continue
            if manager_email:
                linkables[email.lower()] = (user, manager_email)

        # ── Pass 2: resolve reporting lines by manager email ──────────────────
        for email_lower, (user, manager_email) in linkables.items():
            if manager_email == email_lower:
                errors.append({"row": "-", "email": user.email, "error": "A user can't be their own manager."})
                continue
            manager = User.objects.filter(email=manager_email).first()  # tenant-scoped
            if manager is None:
                errors.append({"row": "-", "email": user.email,
                               "error": f"Manager '{manager_email}' not found in this org."})
                continue
            try:
                set_reporting_line(actor, user, manager)
            except Exception as exc:  # noqa: BLE001 — e.g. a reporting cycle
                errors.append({"row": "-", "email": user.email, "error": f"Manager link failed: {exc}"})

    return {
        "created": created, "updated": updated, "skipped": len(errors),
        "total": len(rows), "errors": errors,
    }


def set_display_name(actor, user, display_name) -> User:
    """Set/clear ``user``'s display name (Admin-only). Audited. Blank/None clears it
    (→ the email fallback via ``User.display``)."""
    with tenant_context(user.tenant_id):
        record(
            action="admin.display_name_set",
            actor=actor,
            target_type="user",
            target_id=user.id,
            metadata={"display_name": display_name or None},
            tenant=user.tenant_id,
        )
        user.display_name = display_name or None
        user.save(update_fields=["display_name", "updated_at"])
        return user


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


def list_users(actor, search: str | None = None) -> list[User]:
    """Every user in the actor's tenant (Admin-only), tenant-scoped by the manager,
    ordered by email. Optional ``search`` filters server-side by email / display
    name / role (case-insensitive substring) so the admin table can find a user
    without paging through the whole tenant."""
    from django.db.models import Q

    with tenant_context(actor.tenant_id):
        qs = User.objects.all().order_by("email")
        if search:
            qs = qs.filter(
                Q(email__icontains=search)
                | Q(display_name__icontains=search)
                | Q(role__icontains=search)
            )
        return list(qs)


def user_stats(actor) -> dict:
    """Tenant user counts for the admin dashboard, aggregated IN THE DB.

    The dashboard tiles previously fetched the whole user list just to reduce it
    to a handful of counts — fine for a 20-person tenant, an O(N)-row download for
    a 2k-person one. This returns the same numbers (active total, inactive total,
    active-by-role) in a single GROUP BY, so the dashboard never pulls the list."""
    from django.db.models import Count, Q

    with tenant_context(actor.tenant_id):
        rows = list(
            User.objects.values("role").annotate(
                active=Count("id", filter=Q(is_active=True)),
                total=Count("id"),
            )
        )
    active_by_role = {r["role"]: r["active"] for r in rows}
    total = sum(r["total"] for r in rows)
    active = sum(r["active"] for r in rows)
    return {
        "total": total,
        "active": active,
        "inactive": total - active,
        "active_by_role": active_by_role,
    }


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
        config.version = config.version + 1  # optimistic-lock bump (BUILD_4)
        config.save(update_fields=["settings", "version", "updated_at"])
        return config
