"""
The §2 Roles & Permissions matrix — the single server-side source of truth for
*what a role may do* (capabilities), independent of *what data it may see*
(scopes; see ``scope.py``).

A capability is a coarse, role-gated verb (e.g. "approve a review", "manage the
tenant"). Capabilities are checked on every endpoint server-side — the frontend
is never trusted (CLAUDE.md architecture rule 7). Two capabilities,
``bypass_tenant_isolation`` and ``alter_audit_log``, exist explicitly so the
matrix can state that **nobody** holds them: tenant isolation and the
INSERT-only audit log are inviolable for every role, including Admin
(architecture rules 2 and 5).

This module is pure data + pure functions: no Django, no DB, no I/O. That keeps
it trivially testable and importable from anywhere (views, decorators, tasks).
"""
from __future__ import annotations


class Role:
    """The four PMS roles. Values are the exact strings stored on ``User.role``
    and embedded in the JWT ``role`` claim, so they compare directly against
    ``request.user.role`` with no translation."""

    EMPLOYEE = "EMPLOYEE"
    MANAGER = "MANAGER"
    HRBP = "HRBP"
    ADMIN = "ADMIN"

    #: Every valid role, in increasing order of breadth. Handy for parametrized
    #: tests and for validating an incoming role string.
    ALL = frozenset({EMPLOYEE, MANAGER, HRBP, ADMIN})


class Capability:
    """Capability keys. Use these constants rather than bare strings so typos
    surface at import time instead of silently denying access."""

    VIEW_OWN = "view_own"
    SUBMIT_SELF_EVAL = "submit_self_eval"
    VIEW_TEAM_ANALYTICS = "view_team_analytics"
    MANAGE_REPORTS_GOALS = "manage_reports_goals"
    RUN_AI_REVIEW_DRAFT = "run_ai_review_draft"
    APPROVE_REVIEW = "approve_review"
    BU_ANALYTICS_CALIBRATION = "bu_analytics_calibration"
    SUCCESSION_BENCH_FULL = "succession_bench_full"
    GENERATE_JD = "generate_jd"
    MANAGE_JD_LIBRARY = "manage_jd_library"
    MANAGE_TENANT = "manage_tenant"
    READ_PRIVATE_DATA = "read_private_data"
    # ── Module 2 — Goals & KPI engine ──
    VIEW_OWN_GOALS = "view_own_goals"          # all roles, OWN scope
    UPDATE_OWN_ACTUALS = "update_own_actuals"  # all roles, OWN scope (self-update actuals)
    APPROVE_GOALS = "approve_goals"            # Manager+, TEAM scope
    VIEW_TEAM_SCORES = "view_team_scores"      # Manager TEAM / HRBP+Admin TENANT
    MANAGE_KPI_TEMPLATES = "manage_kpi_templates"  # HRBP, Admin
    CONFIGURE_SCORING = "configure_scoring"    # Admin only
    MANAGE_CYCLES = "manage_cycles"            # HRBP, Admin (cycle CRUD)
    # (Goal create/edit reuses the existing MANAGE_REPORTS_GOALS capability.)
    # ── Module 3 — Reviews & Appraisal Cycles ──
    # (The HITL human approval reuses the existing APPROVE_REVIEW capability.)
    MANAGE_REVIEWS = "manage_reviews"              # Manager+, TEAM — create/edit/draft
    FINALIZE_REVIEW = "finalize_review"            # Manager+, TEAM — post-approval finalize
    VIEW_OWN_REVIEW = "view_own_review"            # all roles, OWN — own finalized review
    SUBMIT_SELF_ASSESSMENT = "submit_self_assessment"  # all roles, OWN
    SUBMIT_ASSESSMENT = "submit_assessment"        # Manager+ — scoped to the review subject
    CALIBRATE_REVIEWS = "calibrate_reviews"        # HRBP, Admin — tenant-wide calibration
    # ── Module 4 — 360° Feedback & anonymisation ──
    MANAGE_FEEDBACK_CYCLE = "manage_feedback_cycle"          # Manager+ — open/close 360s, invite
    GIVE_FEEDBACK = "give_feedback"                          # all — as themselves only
    VIEW_OWN_FEEDBACK_SUMMARY = "view_own_feedback_summary"  # all, OWN — released summary
    APPROVE_FEEDBACK_SUMMARY = "approve_feedback_summary"    # HRBP, Admin — clears holds
    MANAGE_ONE_ON_ONE = "manage_one_on_one"                  # all — participants only (object rule)
    # ── Module 5 — Approval Workflows ──
    CONFIGURE_APPROVAL_WORKFLOW = "configure_approval_workflow"  # Admin, HRBP — design the matrix
    ACT_ON_APPROVAL_STEP = "act_on_approval_step"                # Manager+ — engine enforces assignment
    VIEW_APPROVAL_STATUS = "view_approval_status"                # all — inbox / route tracker
    # ── Module 6 — JD Library & AI JD Generator ──
    # (generate_jd / manage_jd_library already exist above — HRBP+Admin — and are
    # reused. The library write/lifecycle verbs ride on manage_jd_library.)
    REQUEST_JD = "request_jd"            # Manager+ — request HRBP author/generate a JD
    VIEW_JD_LIBRARY = "view_jd_library"  # all — but non-managers see PUBLISHED only (scope)
    # ── Module 7 — Live Org Chart ──
    VIEW_ORG_CHART = "view_org_chart"    # all — scoped OWN (line) / TEAM (subtree) / TENANT
    MANAGE_POSITIONS = "manage_positions"  # HRBP, Admin — create/fill/close vacancies, link JDs
    REASSIGN_REPORTING_LINE = "reassign_reporting_line"  # HRBP, Admin — move a person (cycle-checked)
    # ── Module 8 — Succession & Talent (MANAGEMENT-ONLY; no employee access anywhere) ──
    MANAGE_CRITICAL_ROLES = "manage_critical_roles"  # HRBP, Admin — critical-role registry + risk
    MANAGE_BENCH = "manage_bench"                    # Manager+ (Manager own-tier) — bench + readiness
    ASSESS_NINE_BOX = "assess_nine_box"              # Manager+ (Manager own-tier) — assign potential / place
    OVERRIDE_NINE_BOX = "override_nine_box"          # HRBP, Admin — persisted human override of the computed box
    VIEW_SUCCESSION = "view_succession"              # Manager+ (Manager own report tier ONLY) — NO employees
    GENERATE_SUCCESSION_ANALYSIS = "generate_succession_analysis"  # HRBP, Admin
    PUBLISH_SUCCESSION_PLAN = "publish_succession_plan"            # HRBP, Admin
    # ── Module 9 — Career Development (Roadmap LITE; advisory, employee-visible) ──
    # Career is the friendly counterpart to succession: employees DO see their OWN
    # roadmap/gap. Scope (Employee OWN / Manager TEAM / HRBP+Admin TENANT) is
    # enforced in the services; an out-of-scope target → 404.
    SELECT_TARGET_ROLE = "select_target_role"        # all (own); Manager/HRBP for reports
    VIEW_CAREER_ROADMAP = "view_career_roadmap"      # all (own); Manager TEAM; HRBP TENANT
    MANAGE_CAREER_ROADMAP = "manage_career_roadmap"  # all (own gen/regen); Manager for reports
    # ── Module 11 — Entitlements, Billing & Admin (+ Audit Console) ──
    # MANAGE_TENANT (Admin, above) remains the umbrella admin capability and still
    # gates the existing entitlement/upgrade/seats endpoints; these are granular
    # Admin-only subsets for the new admin surfaces, plus a scoped console read.
    MANAGE_ENTITLEMENTS = "manage_entitlements"      # Admin — feature flags / packs / budgets
    MANAGE_TENANT_CONFIG = "manage_tenant_config"    # Admin — tenant settings
    MANAGE_USERS_ROLES = "manage_users_roles"        # Admin — create/deactivate users, roles, line
    VIEW_AUDIT_CONSOLE = "view_audit_console"        # HRBP (scoped) + Admin (tenant) — READ-ONLY
    # ── Module A — Analytics & Reporting (deterministic; min-cohort ≥ 5) ──
    VIEW_INDIVIDUAL_ANALYTICS = "view_individual_analytics"    # all (own); Manager reports; HRBP/Admin tenant
    VIEW_DEPARTMENT_ANALYTICS = "view_department_analytics"    # Manager line; HRBP/Admin tenant — NEVER Employee
    VIEW_CALIBRATION_GRID = "view_calibration_grid"            # HRBP, Admin
    # ── Module 12 — Integrations (Jira + Slack) ──
    MANAGE_INTEGRATIONS = "manage_integrations"                # Admin — configure/enable per tenant
    # ── Module 10 — AI Agents (Chat Assistant) ──
    # Chat is READ-ONLY + RBAC-bound: this gates "may use chat at all" (everyone);
    # the DATA it can return is bounded by the caller's own scope in the services,
    # and the surface is additionally entitlement-gated ("chat", STARTER).
    USE_CHAT = "use_chat"
    # ── RW_BUILD_2 — Recognition (kudos). Everyone may give + view; the FEED's
    # row visibility (PRIVATE/MANAGER_ONLY/TEAM/COMPANY) is enforced in the
    # recognition services, not by capability. Analytics is aggregate, Manager+. ──
    GIVE_RECOGNITION = "give_recognition"
    VIEW_RECOGNITION = "view_recognition"
    VIEW_RECOGNITION_ANALYTICS = "view_recognition_analytics"
    # ── RW_BUILD_3 — Weekly Check-ins. Everyone manages their OWN check-in; a
    # manager reads + responds to their reports' (scope-bound in the services). ──
    MANAGE_OWN_CHECKIN = "manage_own_checkin"
    VIEW_TEAM_CHECKINS = "view_team_checkins"
    RESPOND_CHECKIN = "respond_checkin"
    # Held by NOBODY — see module docstring. Present so the matrix is explicit
    # that these powers do not exist for any role.
    BYPASS_TENANT_ISOLATION = "bypass_tenant_isolation"
    ALTER_AUDIT_LOG = "alter_audit_log"


# Convenience role groupings used to express the matrix concisely.
_MANAGER_UP = frozenset({Role.MANAGER, Role.HRBP, Role.ADMIN})
_HRBP_UP = frozenset({Role.HRBP, Role.ADMIN})
_ADMIN_ONLY = frozenset({Role.ADMIN})
_EVERYONE = Role.ALL
_NOBODY: frozenset = frozenset()


#: capability key -> frozenset of roles permitted to exercise it.
#:
#: This encodes the §2 matrix exactly. Notes on the spec's parentheticals:
#:  - ``succession_bench_full`` is the *full* bench view; Manager sees only its
#:    own report tier (a scoped, lesser view) and so is modelled as NOT holding
#:    this capability.
#:  - ``generate_jd`` / ``manage_jd_library``: Manager may *request* a JD but not
#:    generate/manage the library, so it is not granted the capability.
#:  - ``read_private_data`` is granted to HRBP and Admin; HRBP's access is
#:    *scoped* (tenant-wide for MVP, see ``scope.py``) and every read is expected
#:    to be audit-logged with a justification by the calling feature.
CAPABILITIES: dict[str, frozenset] = {
    Capability.VIEW_OWN: _EVERYONE,
    Capability.SUBMIT_SELF_EVAL: _EVERYONE,
    Capability.VIEW_TEAM_ANALYTICS: _MANAGER_UP,
    Capability.MANAGE_REPORTS_GOALS: _MANAGER_UP,
    Capability.RUN_AI_REVIEW_DRAFT: _MANAGER_UP,
    Capability.APPROVE_REVIEW: _MANAGER_UP,
    Capability.BU_ANALYTICS_CALIBRATION: _HRBP_UP,
    Capability.SUCCESSION_BENCH_FULL: _HRBP_UP,
    Capability.GENERATE_JD: _HRBP_UP,
    Capability.MANAGE_JD_LIBRARY: _HRBP_UP,
    Capability.MANAGE_TENANT: _ADMIN_ONLY,
    Capability.READ_PRIVATE_DATA: _HRBP_UP,
    # Module 2 — Goals & KPI engine (scope is enforced separately by WithinScope;
    # e.g. VIEW_TEAM_SCORES is held by Manager+ but a Manager only sees their
    # reporting subtree while HRBP/Admin see the whole tenant).
    Capability.VIEW_OWN_GOALS: _EVERYONE,
    Capability.UPDATE_OWN_ACTUALS: _EVERYONE,
    Capability.APPROVE_GOALS: _MANAGER_UP,
    Capability.VIEW_TEAM_SCORES: _MANAGER_UP,
    Capability.MANAGE_KPI_TEMPLATES: _HRBP_UP,
    Capability.CONFIGURE_SCORING: _ADMIN_ONLY,
    Capability.MANAGE_CYCLES: _HRBP_UP,
    # Module 3 — Reviews (scope enforced separately by WithinScope: Manager =
    # reporting subtree, HRBP/Admin = tenant, employees = OWN).
    Capability.MANAGE_REVIEWS: _MANAGER_UP,
    Capability.FINALIZE_REVIEW: _MANAGER_UP,
    Capability.VIEW_OWN_REVIEW: _EVERYONE,
    Capability.SUBMIT_SELF_ASSESSMENT: _EVERYONE,
    Capability.SUBMIT_ASSESSMENT: _MANAGER_UP,
    Capability.CALIBRATE_REVIEWS: _HRBP_UP,
    # Module 4 — Feedback (scope via WithinScope + serializer-level identity
    # stripping; the giver is always server-set to the acting user).
    Capability.MANAGE_FEEDBACK_CYCLE: _MANAGER_UP,
    Capability.GIVE_FEEDBACK: _EVERYONE,
    Capability.VIEW_OWN_FEEDBACK_SUMMARY: _EVERYONE,
    Capability.APPROVE_FEEDBACK_SUMMARY: _HRBP_UP,
    Capability.MANAGE_ONE_ON_ONE: _EVERYONE,
    # Module 5 — Approval Workflows. The engine additionally enforces that the
    # actor is the assigned approver / in-scope role-slot holder for a step.
    Capability.CONFIGURE_APPROVAL_WORKFLOW: _HRBP_UP,
    Capability.ACT_ON_APPROVAL_STEP: _MANAGER_UP,
    Capability.VIEW_APPROVAL_STATUS: _EVERYONE,
    # Module 6 — JD Library. generate_jd / manage_jd_library (HRBP+) are reused
    # from the rows above; these two are new. VIEW_JD_LIBRARY is held by everyone
    # but WithinScope restricts non-managers to PUBLISHED entries.
    Capability.REQUEST_JD: _MANAGER_UP,
    Capability.VIEW_JD_LIBRARY: _EVERYONE,
    # Module 7 — Live Org Chart. view_org_chart is held by everyone but the
    # services scope the rows (OWN line / TEAM subtree / TENANT); position
    # management + reporting-line reassignment are HRBP/Admin (TENANT).
    Capability.VIEW_ORG_CHART: _EVERYONE,
    Capability.MANAGE_POSITIONS: _HRBP_UP,
    Capability.REASSIGN_REPORTING_LINE: _HRBP_UP,
    # Module 8 — Succession & Talent. MANAGEMENT-ONLY: employees hold NONE of
    # these (and the SuccessionParticipant permission turns any employee access
    # into a 404, not a 403). Manager-held caps are additionally scoped to the
    # manager's reporting subtree by the services (out-of-tier target → 404).
    Capability.MANAGE_CRITICAL_ROLES: _HRBP_UP,
    Capability.MANAGE_BENCH: _MANAGER_UP,
    Capability.ASSESS_NINE_BOX: _MANAGER_UP,
    Capability.OVERRIDE_NINE_BOX: _HRBP_UP,
    Capability.VIEW_SUCCESSION: _MANAGER_UP,
    Capability.GENERATE_SUCCESSION_ANALYSIS: _HRBP_UP,
    Capability.PUBLISH_SUCCESSION_PLAN: _HRBP_UP,
    # Module 9 — Career Development. All roles hold these capabilities; the
    # services restrict the rows by scope (an Employee acts only on themselves, a
    # Manager on their reporting subtree, HRBP/Admin tenant-wide).
    Capability.SELECT_TARGET_ROLE: _EVERYONE,
    Capability.VIEW_CAREER_ROADMAP: _EVERYONE,
    Capability.MANAGE_CAREER_ROADMAP: _EVERYONE,
    # Module 11 — Entitlements, Billing & Admin. The three management verbs are
    # Admin-only; the audit console READ is HRBP (scoped tenant-wide in the MVP) +
    # Admin. Nobody can WRITE the audit log (the M1 immutability still governs).
    Capability.MANAGE_ENTITLEMENTS: _ADMIN_ONLY,
    Capability.MANAGE_TENANT_CONFIG: _ADMIN_ONLY,
    Capability.MANAGE_USERS_ROLES: _ADMIN_ONLY,
    Capability.VIEW_AUDIT_CONSOLE: _HRBP_UP,
    # Module A — Analytics. Individual analytics is held by everyone (scoped to
    # OWN for an employee); department analytics is Manager+ (NEVER an employee);
    # the calibration grid is HRBP/Admin. Min-cohort suppression applies on top.
    Capability.VIEW_INDIVIDUAL_ANALYTICS: _EVERYONE,
    Capability.VIEW_DEPARTMENT_ANALYTICS: _MANAGER_UP,
    Capability.VIEW_CALIBRATION_GRID: _HRBP_UP,
    # Module 12 — Integrations. Configuring/enabling a tenant's Jira/Slack is
    # Admin-only; the actual syncs/sends are system-driven (signals / tasks).
    Capability.MANAGE_INTEGRATIONS: _ADMIN_ONLY,
    # Module 10 — Chat Assistant. Everyone may use chat; data is scope-bounded in
    # the services + the surface is entitlement-gated ("chat").
    Capability.USE_CHAT: _EVERYONE,
    # RW_BUILD_2 — Recognition. Give + view are universal (the feed's row
    # visibility is enforced server-side in apps.recognition.services); analytics
    # is Manager+ aggregate-only.
    Capability.GIVE_RECOGNITION: _EVERYONE,
    Capability.VIEW_RECOGNITION: _EVERYONE,
    Capability.VIEW_RECOGNITION_ANALYTICS: _MANAGER_UP,
    # RW_BUILD_3 — Check-ins. Own is universal; reading/responding to reports' is
    # Manager+ (scope enforced in apps.checkins.services).
    Capability.MANAGE_OWN_CHECKIN: _EVERYONE,
    Capability.VIEW_TEAM_CHECKINS: _MANAGER_UP,
    Capability.RESPOND_CHECKIN: _MANAGER_UP,
    Capability.BYPASS_TENANT_ISOLATION: _NOBODY,
    Capability.ALTER_AUDIT_LOG: _NOBODY,
}


def role_has_capability(role: str, capability: str) -> bool:
    """Return True iff ``role`` is permitted to exercise ``capability``.

    Fails closed: an unknown role, an unknown capability, or a ``None`` returns
    False rather than raising, so a misconfigured view denies access instead of
    erroring open. Capability typos are guarded against by using the
    ``Capability`` constants at call sites.
    """
    allowed = CAPABILITIES.get(capability)
    if allowed is None:
        return False
    return role in allowed


def capabilities_for_role(role: str) -> list[str]:
    """Every capability ``role`` may exercise, sorted — derived from the SAME
    matrix ``HasCapability`` enforces. Served to the client on ``/api/auth/me``
    so the UI gates controls off the server's truth (a role that can't perform
    an action never sees its button) instead of re-deriving from the role
    ladder. Unknown role → empty list (fails closed)."""
    return sorted(cap for cap, allowed in CAPABILITIES.items() if role in allowed)
