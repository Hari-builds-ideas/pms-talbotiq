# Frontend Contract — 01 · Screen Inventory

The complete set of screens the product needs. Each block: **purpose · surface ·
roles · endpoints (method · path · capability · scope) · data (serializer +
fields) · actions (→ endpoint → transition) · states · validation.** Every screen
also handles the global states from `00_overview.md` (loading, 401→login,
403→not-permitted, 404→not-yours, 429→retry/upgrade, 503→AI-unavailable) — only
screen-specific deviations are called out. Enum values: see `03_data_dictionary.md`.

---

## 1. Auth & MFA  · Mobile + Desktop · all roles
- **Endpoints:** `POST /api/auth/login`; `POST /api/auth/mfa/challenge`;
  `POST /api/auth/mfa/enroll` + `/mfa/enroll/confirm`; `POST /api/auth/token/refresh`;
  `POST /api/auth/logout`; `GET /api/auth/me`; OIDC at `/accounts/...` +
  `POST /api/auth/oidc/complete`.
- **Data:** `me` → `{id, email, role, tenant, mfa_enabled}`.
- **Actions:** Login → tokens (or MFA-required); Submit TOTP → tokens; Enrol MFA →
  secret/QR → confirm; Logout → blacklist + clear.
- **States:** login form · invalid-credentials (**401**) · MFA-required → TOTP step ·
  MFA-invalid · enrolment (show QR/secret) · SSO redirect · authenticated (route by
  role).
- **Validation:** email format; password present; TOTP 6 digits. Never store/send a
  tenant id beyond the login tenant hint.

## 2. Dashboard (role-scoped landing) · Mobile + Desktop · all roles
- **Purpose:** role-appropriate entry: Employee → my goals/review/feedback/roadmap;
  Manager → team + approvals inbox + my self-service; HRBP/Admin → management tiles.
- **Endpoints (compose from):** `GET /api/auth/me`; for Manager+ the approvals inbox
  count (`GET /api/approvals/inbox`); KPI nudges (`agent2`, if surfaced). No single
  "dashboard" endpoint — the frontend composes tiles from the feature screens below.
- **States:** loading · populated (tiles) · empty (new tenant). Gate premium tiles on
  feature flags.

## 3. Goals & KPIs · Mobile (own) + Desktop (team) · all roles (manage = Manager+)
- **Endpoints:** `GET/POST /api/cycles/…` (cycle list + create + recompute + score
  reads — `manage_cycles` HRBP/Admin for create; `view_team_scores` for reads);
  `GET/POST /api/goals/…` goals (nested KPIs) + manager approve (`manage_reports_goals`,
  `approve_goals`); KPI CRUD; OWN actual-update (`update_own_actuals`, all roles);
  templates list + instantiate (`manage_kpi_templates`).
- **Data:** Goal (`GoalSerializer`: title, description, objective, weight[Decimal],
  status[Goal.Status], cycle, employee, approved_by/at); Kpi (name, weight, target_value,
  direction[INCREASING/DECREASING], unit, source[MANUAL/JIRA], external_ref);
  KpiMeasurement (value, recorded_at, source) — append-only; CycleScore (read-only:
  raw_score, z_score, t_score, cohort_size, risk_status[ON_TRACK/AT_RISK/CRITICAL],
  pace_behind, computed_at).
- **Actions:** Create/edit goal+KPIs → POST/PATCH; Submit own actual → POST actual
  (own only; a peer's → 404); Manager approve goal → `goal.approved`; Recompute scores
  (Manager+) → recompute (whole cohort, idempotent).
- **States:** empty (no goals) · draft vs ACTIVE goal · scores not-yet-computed ·
  populated (show T-score + risk badge + pace_behind) · weight-sum error.
- **Validation (UI must enforce + echo):** **a goal's KPI weights must sum to exactly
  100.00, AND an employee's ACTIVE goals' weights must sum to exactly 100.00** (99.99 /
  100.01 rejected → 422 with the exact message; show a live running-sum indicator).
  `target_value` > 0. All weights/values are Decimal (2dp display) — never float.

## 4. Reviews · Mobile (own, read) + Desktop (manage) · Employee (own) / Manager+ (manage)
- **Endpoints (`/api/reviews/`):** list/create (`manage_reviews`; create requires an
  ACTIVE cycle; reviewer defaults to the acting manager); detail; `…/timeline`;
  assessments (SELF upsert by the subject; MANAGER/PEER/UPWARD by Manager+);
  transitions: `…/start-edit`, `…/submit` (+save-draft), `…/approve` (`approve_review`),
  `…/reject` (reason required), `…/finalize` (`finalize_review`), `…/request-ai-draft`
  (`run_ai_review_draft`); HRBP/Admin `…/calibration?cycle=&state=` (`calibrate_reviews`).
- **Data:** `ReviewSerializer` — employee, reviewer, cycle, **state**[Review.State],
  draft_body, final_body, human_reviewer (null until approved), approved_at,
  finalized_at, rejected_reason, **source**[MANUAL/AI], confidence_score + citations
  (AI only); ReviewStateTransition timeline rows (from/to/action/actor/at).
- **Actions → transition** (see `02_state_machines.md`): Request AI draft → DRAFT→AI_DRAFTING
  (then system → PENDING_HUMAN_REVIEW); Start edit → …→EDITING; Submit → EDITING→PENDING;
  Approve → PENDING→APPROVED (sets human_reviewer); Reject(reason) → PENDING→REJECTED;
  Finalize → APPROVED→FINALIZED (or enters an approval route if one is active).
- **States:** DRAFT · AI_DRAFTING (spinner) · **PENDING_HUMAN_REVIEW (show Approve/Reject/Edit
  + draft badge + confidence + low-confidence warning)** · EDITING · APPROVED · REJECTED
  (show reason) · FINALIZED (read-only; employees can read their own) · 409 illegal action
  (re-fetch) · 422 HITL/REASON · **503** request-ai-draft when Agent 1 not configured (the
  manual path still works) · **403** if the tenant lacks the `agent1` feature (now FULL_AI).
- **Validation:** reject requires a non-empty reason (422 `REJECTION_REASON_REQUIRED`);
  finalize without approval → 422 `HITL_APPROVAL_REQUIRED`; never show a draft as final.

## 5. 360 Feedback — cycles, give, requests, summary, 1:1 notes · Mobile (give/own) + Desktop (run) · all roles
- **Endpoints (`/api/feedback/`):** cycles CRUD + open/close + `…/summarize`
  (`manage_feedback_cycle` Manager+); invitations (cycle requests + `requests/mine` +
  decline); `…/give` (invitation-authorised, giver server-set, `give_feedback`);
  continuous; `mine`/`received` (received is giver-less); the subject's anonymised view
  (CLOSED only) + released summary (`view_own_feedback_summary`; 403 SUMMARY_NOT_RELEASED
  until released); HRBP review queue + approve (`approve_feedback_summary`); 1:1 notes
  (participants ONLY — even Admin denied).
- **Data:** FeedbackCycle (subject, status[DRAFT/COLLECTING/CLOSED], min_volume);
  FeedbackRequest (relationship[SELF/MANAGER/PEER/UPWARD], status[PENDING/SUBMITTED/DECLINED]);
  Feedback (body, relationship, kind[THREE_SIXTY/CONTINUOUS]; **giver NEVER egressed**);
  the anonymised payload (pseudonyms PEER#1…, `insufficient_groups`, NO giver ids);
  FeedbackSummary (sections[strengths/growth/themes/risks] — **NULL until Agent 3**,
  status[PENDING_HUMAN_REVIEW/HRBP_HOLD/APPROVED/RELEASED], anonymity_passed, confidence_score);
  OneOnOneNote (participants-only, not anonymised, not summarised).
- **Actions:** Invite giver → request (PENDING); Give feedback → submit (request→SUBMITTED);
  Decline → DECLINED; Close cycle → triggers summarize (Agent 3 seam → 503 if unconfigured);
  HRBP review → Approve/Release (HRBP_HOLD/PENDING → RELEASED).
- **States:** cycle DRAFT/COLLECTING/CLOSED · my pending invitations · giver-attributed (own
  give) vs **giver-less** (received) · anonymised view (CLOSED only; show pseudonyms +
  `insufficient_groups` "too few responses" markers) · summary PENDING/**HRBP_HOLD**
  (breach/sensitive — HRBP must review) /APPROVED/RELEASED · summary sections NULL =
  "not generated" (never fabricate) · 403 SUMMARY_NOT_RELEASED.
- **Validation:** a SELF invitation only for the subject; the subject can only receive
  SELF; one invitation per giver per cycle; the UI must NEVER render a giver identity on a
  received/anonymised view.

## 6. Approvals — inbox, route tracker, workflow designer · Desktop · Manager+ (config = HRBP/Admin)
- **Endpoints (`/api/approvals/`):** workflow CRUD + activate/deactivate
  (`configure_approval_workflow`); approver `inbox` (SEQUENTIAL surfaces only the active
  step); route `tracker` (`/routes/<id>`, `/routes?artifact_type=&artifact_id=`);
  `steps/<id>/approve|reject` (`act_on_approval_step`; the engine also enforces the actor
  is the assigned approver / in-scope slot holder).
- **Data:** ApprovalWorkflow (name, artifact_type, mode[SEQUENTIAL/PARALLEL], active);
  ApprovalStep (order, approver_kind[ROLE/NAMED], approver_role, approver_user, required,
  timeout_hours, escalation_role/user); ApprovalRoute (status[IN_PROGRESS/APPROVED/REJECTED/
  ESCALATED], mode, initiated_by); ApprovalStepInstance (order, approver, approver_role,
  status[PENDING/APPROVED/REJECTED/ESCALATED/SKIPPED], due_at, escalated, decided_by/at, comment).
- **Actions → transition** (see `02_state_machines.md`): Approve step → advances / completes
  the route; Reject step → REJECTED (ends route); Activate/deactivate a workflow.
- **States:** inbox empty vs items (SEQUENTIAL = only the active step shows) · tracker
  stepper (per-step status, due_at, escalated badge) · 409 out-of-order / already-decided
  (re-fetch) · 403 not-the-assigned-approver.
- **Validation:** a step decision requires the actor be the assignee (engine-enforced —
  surface 403/409 cleanly); the workflow designer enforces at-most-one ACTIVE workflow per
  artifact_type (see `05_open_questions.md` re: designer scope).

## 7. JD Library — browse, editor, version history, requests · Desktop (author) + Mobile (browse) · Manager+ (browse) / HRBP+ (author)
- **Endpoints (`/api/jd/`):** `GET/POST /` (list/create); detail + `…/versions` + `…/export`
  (`view_jd_library`; non-managers see PUBLISHED only — a draft → 404); lifecycle
  `…/save-draft|submit|approve|revise|archive` (`manage_jd_library`); `…/generate`
  (`generate_jd` — **503** seam / 422 inputs / 409 / 201; gated `jd_generator` = FULL_AI);
  templates + `…/instantiate`; `requests` (GET/POST `request_jd`) + `requests/<id>/fulfil|decline`.
- **Data:** JobDescription (title, level, department, **status**[DRAFT/PENDING_HUMAN_REVIEW/
  IN_REVIEW/PUBLISHED/ARCHIVED], source[MANUAL/AI], current_version, created_by);
  JDVersion (version_number, body{summary, responsibilities[], must_haves[], nice_to_haves[]},
  confidence_score+citations[AI], is_published); JDRequest (title, level, notes,
  status[OPEN/FULFILLED/DECLINED]).
- **Actions → transition** (see `02`): Save draft; Submit → PENDING; Approve → PUBLISH (or
  enter route → IN_REVIEW); Generate (AI) → writes body, locks PENDING; Revise published →
  new DRAFT version (published stays live + frozen); Archive.
- **States:** browse list (PUBLISHED only for non-managers) · editor (working version) ·
  version history (current_version = live published, immutable) · generate → 503 (Agent
  not configured) / 422 INVALID_JD_INPUT / 403 (no `jd_generator` feature) · request OPEN/
  FULFILLED/DECLINED.
- **Validation:** title + level + body (summary/responsibilities/must_haves) required to
  submit (422); export is text/JSON only (no binary).

## 8. Org Chart — tree, person card, vacancies, reassign, positions · Desktop · all (scoped); manage = HRBP/Admin
- **Endpoints (`/api/org/`):** `GET /tree` (nodes+edges+roots+rollups), `/people/<id>`
  (404 out-of-scope), `/search?q=`, `/export`, `/vacancies` (`view_org_chart`, scoped);
  positions `GET/POST /positions`, `/positions/<id>`, `/positions/<id>/fill|close|link-jd|unlink-jd`
  (`manage_positions`); `POST /reassign` (`reassign_reporting_line`).
- **Data:** tree node (user id, email, role, headcount[subtree], vacancies[OPEN positions
  in subtree]); Position (title, reports_to, department, status[OPEN/FILLED/CLOSED],
  filled_by, published_jd, opened_at, filled_at).
- **Actions → transition:** Create position (OPEN); Fill → FILLED (409 if already filled);
  Close → CLOSED; Link/unlink a PUBLISHED JD; Reassign a person's manager (cycle-checked).
- **States:** scoped tree (Employee = own line; Manager = subtree; HRBP/Admin = tenant,
  multiple roots) · person card 404 if out of scope · vacancies list · 409 illegal position
  transition · **422 REPORTING_CYCLE** on a reassignment that would loop.
- **Validation:** reassignment target must be active + in-tenant + not the user / not in the
  user's subtree (422 REPORTING_CYCLE); a linked JD must be PUBLISHED (422).

## 9. Succession — dashboard, 9-box, bench, plan review · **Desktop ONLY · MANAGEMENT-ONLY** (Manager own-tier / HRBP+ tenant; **Employee → 404 everywhere**)
- **Endpoints (`/api/succession/`):** `dashboard` (`view_succession`); critical-roles CRUD +
  `…/knowledge-risk` + `…/archive` (`manage_critical_roles` HRBP+); `…/bench` list/add
  (`manage_bench` Manager+, scoped) + `bench/<id>/readiness`; `nine-box` list/assess
  (`assess_nine_box`); `…/generate` (`generate_succession_analysis` HRBP+); plan
  `plans/<id>` + `…/action-item` + `…/publish` (`publish_succession_plan` HRBP+); `…/enrich`
  (Agent 4 seam → **503**).
- **Data:** CriticalRole (name, position, incumbent, criticality[HIGH/CRITICAL],
  knowledge_risk[LOW/MEDIUM/HIGH], status[ACTIVE/ARCHIVED]); BenchCandidate (candidate,
  readiness[READY_NOW/READY_SOON/DEVELOPING/NOT_READY], readiness_overridden); NineBoxPlacement
  (employee, cycle, performance_band[LOW/MEDIUM/HIGH derived], potential_band[human-assigned],
  box 1–9); SuccessionPlan (status[DRAFT/PENDING_HUMAN_REVIEW/PUBLISHED], ranked_bench,
  coverage_status[RED/AMBER/GREEN], red_flags, action_items, source[DETERMINISTIC/AI],
  confidence_score).
- **Actions → transition** (see `02`): Mark critical role; Add bench; Set readiness (override
  sticks); Assess 9-box (potential human-assigned, performance derived); Generate analysis →
  PENDING_HUMAN_REVIEW; Add action item (PENDING only); Publish → PUBLISHED; Enrich (Agent 4)
  → new source=AI plan PENDING (deterministic intact) or 503.
- **States:** **employee → 404 on EVERYTHING (the module must be absent from their UI)** ·
  Manager sees own-tier only (out-of-tier → 404) · Manager lacking the HRBP cap → 403 ·
  dashboard coverage RED/AMBER/GREEN per role · plan PENDING (show action-item + publish) ·
  9-box grid · enrich → 503.
- **Validation:** publish only from PENDING (409 ILLEGAL_PLAN_TRANSITION); add action item only
  while PENDING; coverage RED shows the INADEQUATE_COVERAGE red flag.

## 10. Career Roadmap — roadmap, skill-gap, progress · Mobile + Desktop · all (own); Manager+ (reports)
- **Endpoints (`/api/career/`):** `POST /target`; `GET /roadmap` (own); `GET /roadmaps[?employee=]`;
  `GET /roadmaps/<id>`; `GET /roadmaps/<id>/skill-gap`; `POST /roadmaps/<id>/regenerate`;
  `POST /roadmaps/<id>/enrich` (Agent → 503; gated `career_roadmap` = FULL_AI);
  `GET,POST /roadmaps/<id>/progress`.
- **Data:** TargetRoleSelection (employee, target_jd | target_position, selected_by/at);
  DevelopmentRoadmap (status[DRAFT/ACTIVE/ARCHIVED], tiers[{index,title,detail,basis}],
  skill_gap{current_performance_band, required_performance_band, performance_band_gap,
  weak_categories}, source[DETERMINISTIC/AI], **advisory ALWAYS true**, confidence_score);
  RoadmapProgress (tier_index, status[NOT_STARTED/IN_PROGRESS/DONE]).
- **Actions → transition** (see `02`): Select target → creates the deterministic ACTIVE
  roadmap; Regenerate → refresh tiers; Enrich (AI) → new source=AI DRAFT for acceptance
  (503 if unconfigured); Mark tier progress.
- **States:** no target yet (prompt to select) · roadmap ACTIVE (show tiers + skill-gap +
  per-tier progress) · enrich → 503 · **the response NEVER contains succession data**
  (no readiness/potential/bench) — display only performance band + weak categories + tiers.
- **Validation:** exactly one of target_jd / target_position (422 TARGET_AMBIGUOUS); a target
  JD must be PUBLISHED (422 TARGET_NOT_PUBLISHED); progress tier_index within range (422).

## 11. Analytics — individual, department, calibration grid, export · Desktop (dept) + Mobile (own) · scoped
- **Endpoints (`/api/analytics/`):** `GET /individual[?employee=]` (`view_individual_analytics`
  all; own-scoped for Employee); `GET /department?head=&cycle=` (`view_department_analytics`
  Manager+, NEVER Employee); `GET /calibration?cycle=` (`view_calibration_grid` HRBP/Admin);
  `GET /export?head=&cycle=&format=json|text`.
- **Data:** individual trend (per-cycle t_score, risk_status, raw_score, pace_behind);
  department (`cohort_size`, `min_cohort`=5, `suppressed`[bool], aggregate{headcount, scored,
  mean_t_score, median_t_score, risk_distribution}, individuals[] — **empty when suppressed**);
  calibration (grid{box 1–9 → count}, total, placements).
- **Actions:** filter by cycle / head / employee; export (text or JSON download).
- **States:** own trend (Employee) · **department < 5 members → `suppressed:true`, aggregate
  ONLY (UI must NOT show individuals) + a "cohort too small (<5)" marker** · ≥5 → full
  individuals · Employee hitting /department → 403 · calibration HRBP/Admin only (else 403) ·
  cross-tenant/cycle → empty.
- **Validation:** `cycle` is required on /department + /calibration (400 if missing); the UI
  must respect `suppressed` and never render individual values when true.

## 12. Admin — users/roles, tenant config · Desktop · ADMIN only
- **Endpoints (`/api/admin/`):** `GET,POST /users`; `POST /users/<id>/role|deactivate|reactivate|
  reporting-line`; `GET,PUT /tenant-config` (`manage_users_roles` / `manage_tenant_config`).
- **Data:** user (id, email, role[EMPLOYEE/MANAGER/HRBP/ADMIN], manager, is_active, mfa_enabled);
  TenantConfig (settings{} free-form JSON).
- **Actions:** Create user ({email, role, manager?, password?}); Set role; Deactivate/Reactivate;
  Set reporting line (reuses the org cycle-check → 422 REPORTING_CYCLE); Edit tenant settings.
- **States:** user list · create form · 422 EMAIL_TAKEN / UNKNOWN_ROLE · 404 cross-tenant user ·
  403 for any non-Admin.
- **Validation:** valid role; unique email per tenant; reassignment cycle-checked.

## 13. Audit Console · Desktop · HRBP + Admin · READ-ONLY
- **Endpoints (`/api/audit/`):** `GET /logs?actor=&action=&target_type=&target_id=&date_from=&
  date_to=&page=&page_size=` (`view_audit_console`). Paginated (default 50, max 200). **No
  write surface — POST/PUT/DELETE → 405.**
- **Data:** AuditLog (id, actor, action, target_type, target_id, justification, metadata,
  created_at) — all read-only; response `{count, next, previous, results[]}`.
- **Actions:** filter (actor / action / target / date range); paginate. NO edit/delete.
- **States:** empty · filtered results · paginated · 403 for non-HRBP/Admin. The UI must offer
  NO mutation controls (the log is immutable by design).

## 14. Integrations Config · Desktop · ADMIN only
- **Endpoints (`/api/integrations/`):** `GET /` (list); `GET,PUT /<kind>` (JIRA|SLACK)
  (`manage_integrations`).
- **Data:** TenantIntegration (kind[JIRA/SLACK], enabled, config{base_url/email/project/channel/
  value_field…}, **secret_ref** = the NAME of an env var — **never the token**, never returned).
- **Actions:** Enable/disable; edit non-secret config; set `secret_ref`. The UI captures a
  secret-NAME, NOT a secret value (tokens live in the environment/secrets manager).
- **States:** not-configured (GET <kind> → 404) · configured/enabled/disabled · 400 unknown kind ·
  403 non-Admin. Show "secret managed out-of-band" — never display or request a raw token.

## 15. Billing / Entitlements + Upgrade modal · Desktop · ADMIN only
- **Endpoints (`/api/billing/`):** `GET /entitlement`; `POST /upgrade`; `PATCH /seats`
  (`manage_tenant`); `GET /feature-flags`; `GET /upgrade-prompt` (`manage_entitlements`).
- **Data:** Entitlement (seat_count, feature_packs[], unlocked_agents[], tier_label[display
  only]); feature-flags map `{feature: bool}`; upgrade-prompt {current_packs, tier_label,
  feature_flags, locked_features[], upgrade{pack:FULL_AI, would_unlock[], note}}.
- **Actions:** Set seats (independent of packs); Upgrade to FULL_AI (flips flags instantly,
  seats unchanged); show the upgrade modal from upgrade-prompt.
- **States:** STARTER (locked premium list) · FULL_AI (all unlocked) · seats editor · upgrade
  modal (would_unlock list; **conceptual — no pricing/payment**). 403 for non-Admin.
- **Validation:** seat_count ≥ 0 integer. The upgrade is conceptual (no payment capture, Phase 2).

## 16. AI Chat panel · Mobile + Desktop · all (entitlement `chat` = STARTER)
- **Endpoints (`/api/ai/`):** `POST /chat` `{query}` (`use_chat` + `requires_entitlement("chat")`).
- **Data:** response `{status, intent, answer, data?}` — `status` ∈ ok | blocked (write
  intent) | (HTTP 503 not-configured / 429 budget).
- **Actions:** send a natural-language query → a read-only, RBAC-bound answer.
- **States:** answer (read-only; renders only what the caller may see) · **write/approval
  intent → blocked** (show "I can't make changes") · **503** when no LLM provider (show "Chat
  not available yet") · **429** when the chat budget is exhausted (Retry-After) · empty query → 400.
- **Validation:** non-empty query. The UI must treat chat as advisory + read-only — it never
  shows data the user couldn't reach directly, and never offers a "do it for me" write action.
