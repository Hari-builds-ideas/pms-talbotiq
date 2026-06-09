# BUILD NOTES

Append-only log of what each module delivered, per CLAUDE.md.

---

## Module 1 — Foundation (Identity, Access & Tenancy)

**Status:** ✅ Complete. **201 tests passing** on the locked stack (Django 4.2 +
DRF, MySQL 8, Redis 7, Celery, simplejwt, django-allauth, django-otp, Argon2)
inside Docker. Build contract: `docs/Document_2_..._Specification.md` §Module 1,
§2 (Roles & Permissions), §3 (System-wide Conventions), §Module 13 (Admin & Billing).

### What was built

**Project scaffold & infra**
- `config/` settings split (`base` / `dev` / `prod` / `test`), `celery.py`,
  `urls.py`, `wsgi.py`, `asgi.py`. DRF + simplejwt configured; Argon2 is the
  default password hasher; Redis is cache + session store + Celery broker/result
  backend (**no Kafka** — Redis is the only broker for MVP, overriding the spec's
  §4 diagram per CLAUDE.md). Structured JSON logging.
- `requirements.txt` / `requirements-dev.txt` (pinned), `Dockerfile`,
  `docker-compose.yml` (web, mysql8, redis7, celery-worker, celery-beat),
  `db/init.sql`, `.env.example` (every env var documented), `pytest.ini`.
- `apps/core`: `/healthz` liveness endpoint + tests.

**Tenancy core (`apps/tenancy`)** — the isolation foundation
- `Tenant` (UUID pk, name, slug, status) and `TenantScopedModel` abstract base
  (UUID pk, tenant FK, created/updated/deleted timestamps, **soft delete**).
- `TenantScopedManager` / `TenantScopedQuerySet`: every read auto-scoped to the
  current tenant and **fails closed** (returns nothing, never the whole table)
  when no tenant is bound; soft-deleted rows hidden by default.
- Current tenant lives in a **contextvar** set ONLY from the cryptographically
  verified JWT claims by `TenantMiddleware` — never from headers/body/query.
- `save()` enforces write-side isolation: you can only write into the bound
  tenant; cross-tenant writes raise; no-context+no-tenant writes raise.
- One escape hatch, `.all_tenants()`, for system/migration code only — it
  **raises if called on any request path** (a request-active contextvar guards it).

**Identity & auth (`apps/identity`)**
- Custom `User` on `TenantScopedModel` + `AbstractBaseUser`/`PermissionsMixin`:
  UUID pk, tenant FK, `email` (**unique per tenant**), `role`
  {EMPLOYEE, MANAGER, HRBP, ADMIN}, `manager` self-FK (org/reporting tree),
  `mfa_enabled`, `is_active`. Argon2 hashing.
- JWT (simplejwt) with custom claims embedding `tenant_id` + `role` + `email` on
  both access and refresh tokens; claims survive refresh-token rotation.
- Endpoints (`/api/auth/…`): `login` (tenant-qualified local creds → 401 on bad
  creds), `token/refresh`, `logout` (refresh blacklist + session flush),
  `mfa/enroll`, `mfa/enroll/confirm`, `mfa/challenge`, `me`, `oidc/complete`.
  Login enforces MFA only when `user.mfa_enabled`; sessions written to Redis.
- OAuth/OIDC via django-allauth generic OIDC provider configured entirely from
  env (demoable with placeholder config). `TenantSocialAccountAdapter` maps a
  verified OIDC identity to an existing tenant user (resolves tenant from a
  `?tenant=<slug>` hint / session / configured default), denying 403 for unknown
  identities; the IdP never provisions accounts.
- `TenantModelBackend` resolves the session principal by globally-unique pk on
  the SSO bootstrap (the scoped manager fails closed before a tenant is bound).

**RBAC engine (`apps/rbac`)** — implements the §2 matrix server-side
- `matrix.py`: the capability→roles table (the single source of truth);
  `bypass_tenant_isolation` / `alter_audit_log` map to **nobody**.
- `scope.py`: data scopes OWN (employee) / TEAM (manager's reporting subtree,
  transitive) / TENANT (HRBP, Admin), with cross-tenant defence-in-depth.
- DRF `HasCapability` (role/verb gate) + `WithinScope` (object/row gate),
  `RBACMixin`, `requires_capability` decorator. Out-of-scope targets (e.g. a
  peer record) → 403.

**Audit log (`apps/audit`)** — immutable, enforced at two layers
- Append-only `AuditLog` (UUID pk, tenant, actor, action, target, justification,
  metadata JSON, created_at; `db_table = "audit_log"`).
- App layer: queryset `update()`/`delete()` and re-`save()` of an existing row
  all raise `AuditLogImmutableError`.
- DB layer: migration `0002` adds MySQL `BEFORE UPDATE` / `BEFORE DELETE`
  triggers that `SIGNAL SQLSTATE '45000'` — proven to reject even raw SQL.
- `services.record(...)` writer + `audit_action(...)` context manager (writes
  the record before the side effect).

**Billing & entitlements (`apps/billing`)** — decoupled commercial model
- `Entitlement` per tenant with **independent** `seat_count` (int) and
  `feature_packs` (set of pack codes). "Tier" is a display label only.
- Pack registry: `STARTER → {agent1, agent2}`, `FULL_AI → {agent1…agent5}`.
- `requires_entitlement(agent_code)` DRF gate (API-level feature flag);
  `upgrade_to_full_ai()` adds the FULL_AI pack — unlocking agents 3–5 instantly
  **without touching seat_count** — and audits the change (admin-only endpoint).

### Files created
Full app trees under `apps/{core,tenancy,identity,rbac,audit,billing}/` (models,
managers, services, serializers, views, urls, permissions, migrations as
applicable) plus `apps/testsupport/` (test-only concrete `TenantScopedModel`),
`config/` (settings/celery/urls/wsgi/asgi), root `conftest.py`, infra files
(`Dockerfile`, `docker-compose.yml`, `db/init.sql`, `requirements*.txt`,
`.env.example`, `pytest.ini`, `.gitignore`, `.dockerignore`).

### Tests written and passing (201 total, MySQL-backed)
- tenancy 11 (cross-tenant read/write impossible, fail-closed, soft delete,
  all_tenants request-path guard).
- identity 29 (login success/MFA/401 paths, MFA enroll+confirm+challenge, refresh
  claim preservation, logout blacklist, session-to-store, OIDC mapping +
  complete, Argon2, email-unique-per-tenant, reporting line).
- rbac 89 (every role × every capability incl. nobody-bypass; OWN/TEAM/TENANT
  scope incl. manager-vs-peer 403 and cross-tenant denial; end-to-end HTTP via JWT).
- audit 15 (insert/select scoping, app-level immutability, **DB-trigger
  immutability against raw SQL**, writer tenant resolution).
- billing 27 (seats↔packs independence, locked agents denied → unlocked after
  upgrade, seat_count preserved across upgrade, admin-only 403, audit on upgrade).
- core 2 (/healthz).

### How to run
```bash
docker compose up -d --build              # bring up the stack
docker compose run --rm web pytest        # full suite (creates a MySQL test DB)
docker compose run --rm web python manage.py migrate   # apply migrations
```
Tests force `config.settings.test` via `pytest.ini` `--ds` (highest precedence,
above the `DJANGO_SETTINGS_MODULE` env var compose sets to dev).

### Known risks / TODOs
- **HRBP scope = tenant-wide (MVP approximation).** §2 describes HRBP as
  "business-unit wide", but there is no `BusinessUnit` model yet, so HRBP shares
  Admin's data *scope* (they differ on *capabilities*). When BU lands, revisit
  only `scope_for_role` + the TENANT branch of `actor_can_access`.
- **Deployment requirement for audit triggers.** Creating the `audit_log`
  triggers needs `log_bin_trust_function_creators=1` (set on the mysql service in
  compose) OR granting the migrating user `SUPER`/`TRIGGER` when binary logging is
  on. A managed prod MySQL must set this before `migrate`.
- **Soft-delete + email uniqueness.** `(tenant, email)` uniqueness is a plain
  constraint (MySQL has no partial indexes), so a soft-deleted user keeps its
  email reserved until hard-deleted. Acceptable for MVP; revisit if re-using
  emails of deactivated users becomes a requirement.
- **OIDC live round-trip.** The generic OIDC provider is wired and configured
  from env, and the tenant-mapping adapter + post-login JWT mint are unit/E2E
  tested; a full browser round-trip against a real IdP is integration-level and
  not exercised here (SAML is Phase 2 per spec).
- Local host runs Python 3.14 (Django 4.2 won't run there) and has no MySQL/Redis
  client — **all dev/test goes through Docker** (python:3.11 + mysql8 + redis7).
  Host ports remapped to 3307 (mysql) / 6380 (redis) to avoid local clashes.

### What Module 2 (Goals & KPIs) needs from this
- Inherit `apps.tenancy.models.TenantScopedModel` for every new model (gets UUID
  pk, tenant FK, soft delete, scoped manager + write isolation for free).
- Gate endpoints with `apps.rbac`: `RBACMixin` + a `Capability` (e.g.
  `manage_reports_goals`, `view_team_analytics`) and `WithinScope` for row-level
  checks against the reporting tree. Add new capability keys to `rbac/matrix.py`.
- Write audit rows via `apps.audit.services.record(...)` before consequential
  actions; never mutate audit rows.
- Gate AI-agent features with `apps.billing.gate.requires_entitlement("agentN")`
  (Agent 2 — KPI Intelligence is `agent2`, in STARTER).
- Resolve the current user/tenant from `request.user` / `request.user.tenant`;
  the tenant context is already bound by `TenantMiddleware` from the JWT.
- Reporting-tree helpers: `apps.rbac.scope.reporting_subtree_ids(manager)` and
  `User.manager` / `User.reports`.
