# RBAC_MATRIX — the complete permissions matrix (server-grounded)

Ground truth: `apps/rbac/matrix.py` (the `CAPABILITIES` dict), enforced by
`HasCapability` (`apps/rbac/permissions.py:53-75`, **fails closed** — no capability declared → deny;
unknown role/capability → deny) + row scope via `actor_can_access` (`apps/rbac/scope.py:102-130`).
Since this run, the same matrix is **served to the client** on `GET /api/auth/me` as `capabilities`
(`capabilities_for_role`, `apps/rbac/matrix.py`) — the UI gates controls off it (see AUTHZ_UI_ISSUES.md).

## Roles & data scope
| Role | Data scope (`_SCOPE_BY_ROLE`, scope.py:52-57) |
|---|---|
| EMPLOYEE | OWN (self only) |
| MANAGER | TEAM (self + reporting subtree) |
| HRBP | TENANT (v1: same data scope as Admin; differs in capabilities) |
| ADMIN | TENANT |
Cross-tenant is always denied first, regardless of role. `bypass_tenant_isolation` and
`alter_audit_log` are granted to **NOBODY** (inviolable).

## Capability → roles (the full matrix, matrix.py:157-260)
Legend: E=Employee, M=Manager, H=HRBP, A=Admin. "M+"=M,H,A; "H+"=H,A.

| Capability | Roles | | Capability | Roles |
|---|---|---|---|---|
| view_own / submit_self_eval | ALL | | manage_feedback_cycle | M+ |
| view_own_goals | ALL | | give_feedback / view_own_feedback_summary | ALL |
| update_own_actuals | ALL (OWN-only) | | approve_feedback_summary | H+ |
| manage_reports_goals / approve_goals | M+ | | manage_one_on_one | ALL (participants) |
| view_team_scores / view_team_analytics | M+ | | configure_approval_workflow | H+ |
| manage_kpi_templates / manage_cycles | H+ | | act_on_approval_step | M+ (assignee-checked) |
| configure_scoring | A | | view_approval_status | ALL |
| manage_reviews / approve_review / finalize_review | M+ | | request_jd | M+ |
| run_ai_review_draft / submit_assessment | M+ | | view_jd_library | ALL (non-mgr: published) |
| view_own_review / submit_self_assessment | ALL | | generate_jd / manage_jd_library | H+ |
| calibrate_reviews / view_calibration_grid | H+ | | view_org_chart | ALL (scoped) |
| view_individual_analytics | ALL (scoped) | | manage_positions / reassign_reporting_line | H+ |
| view_department_analytics | M+ (never E) | | manage_critical_roles / override_nine_box | H+ |
| bu_analytics_calibration | H+ | | manage_bench / assess_nine_box / view_succession | M+ (own tier) |
| use_chat / give_recognition / view_recognition | ALL | | generate_succession_analysis / publish_succession_plan | H+ |
| view_recognition_analytics | M+ | | succession_bench_full | H+ |
| manage_own_checkin | ALL | | select_target_role / view_career_roadmap / manage_career_roadmap | ALL (scoped) |
| view_team_checkins / respond_checkin | M+ | | manage_tenant / manage_entitlements / manage_tenant_config | A |
| view_audit_console | H+ | | manage_users_roles / manage_integrations | A |
| read_private_data | H+ | | bypass_tenant_isolation / alter_audit_log | **NOBODY** |

## Per-role summary (pages / actions / must-never-see)
- **EMPLOYEE** — pages: dashboard (own cockpit), goals (own), reviews (own, read-only), feedback (give +
  own summary), check-ins (own), recognition, chat. Actions: record own KPI actuals, goal updates, self
  assessment, give feedback/recognition, own check-in, 1:1s, chat (read + propose; execution
  server-gated). Never: any approve/finalize, team/department data, admin, audit, succession,
  calibration, JD authoring.
- **MANAGER** — everything Employee has, plus: create/edit/approve goals for the subtree; create reviews,
  AI drafts, approve/reject/finalize (subject in subtree); open/close 360 cycles for the subtree; respond
  to check-ins; team scores/analytics; approvals inbox (assigned steps); request JD; bench/nine-box for
  own tier. Never: calibration grid, JD authoring/publish, positions/reassign, audit console, admin.
- **HRBP** — tenant-wide data scope plus: cycles, KPI templates, calibration, summary release gate,
  approval workflow config, positions/reassignment, critical roles/succession publish, JD authoring,
  audit console (read-only). Never: user/role management, entitlements, tenant config, integrations.
- **ADMIN** — everything HRBP has (tenant scope) plus users & roles, entitlements/billing, tenant
  config, integrations, scoring config. Never: bypass tenant isolation, alter audit rows (nobody can).

## Endpoint capability spot-map (representative; full sweep in the audit)
Goals list/read `view_own_goals` (scoped) · goal create/edit `manage_reports_goals` + `actor_can_access` ·
approve `approve_goals` · **record actual `update_own_actuals` + explicit OWN check** (a manager 403s on a
report's KPI — deliberately self-service) · reviews transitions re-checked in the state machine
(capability + scope, `apps/reviews/state_machine.py:101-108`) · approvals decision re-checks the assigned
approver · AI chat `use_chat` with all writes through the audited execute gate · billing `my-features` is
auth-only (any role) — it's the paywall map, not RBAC.
