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
