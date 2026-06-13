# Frontend Contract — 03 · Data Dictionary

The shared vocabulary. Each entity lists its frontend-relevant fields, types, enum
values, and whether the field is **read-only** (server-set; display only) or
**settable** (the client supplies it on create/action). The authoritative shape is
each app's `serializers.py`; this is the index + every enum's full value set.

Conventions: all ids are **UUID** strings. All money/weight/ratio values are
**Decimal strings** (2dp display) — never parse as float for arithmetic you send
back. Timestamps are ISO-8601 (see `05_open_questions.md` re: timezone display).
`tenant` is implicit (from the JWT) and never sent by the client.

---

## Identity & tenancy
- **User** (`/api/auth/me`, admin `UserAdminSerializer`, org person card/search):
  `id`, `email`, `display_name` (string|null — optional, settable via the Admin Hub),
  `display` (string — the **effective** name = `display_name` or email fallback;
  **render this**), `role` ∈ **EMPLOYEE · MANAGER · HRBP · ADMIN**, `manager`
  (UUID|null), `is_active` (bool), `mfa_enabled` (bool). Read-only to the client
  except via the Admin Hub (create with `display_name`; set role / active /
  reporting-line / **display-name**). Use `display` for rendering (always populated);
  `display_name` for editing.
- **Tenant**: `id`, `name`, `slug`, `status` ∈ **ACTIVE · SUSPENDED · CANCELLED**.
  Read-only to the frontend (provisioning/admin concern).
- **TenantConfig** (`administration`): `settings` (free-form JSON object) — settable
  by Admin via PUT.

## Cycles, goals, KPIs (Module 2)
- **PerformanceCycle**: `id`, `name`, `start_date`, `end_date`,
  `status` ∈ **DRAFT · ACTIVE · CLOSED**. Create/manage = HRBP/Admin.
- **Goal** (`GoalSerializer`): `title`, `description`, `objective`, `weight` (Decimal,
  0–100), `status` ∈ **DRAFT · ACTIVE · ACHIEVED · MISSED · ARCHIVED**, `cycle`,
  `employee`, `created_by`, `approved_by`/`approved_at` (read-only). Settable:
  title/description/objective/weight (Manager+).
- **Kpi**: `name`, `description`, `weight` (Decimal), `target_value` (Decimal >0),
  `direction` ∈ **INCREASING · DECREASING**, `unit`, `source` ∈ **MANUAL · JIRA**,
  `external_ref` (Jira key when source=JIRA). Settable nested under a Goal.
- **KpiMeasurement** (append-only): `value` (Decimal), `recorded_at`, `recorded_by`,
  `source` ∈ **MANUAL · JIRA · SYSTEM**. Settable: `value` (own actuals only).
- **CycleScore** (read-only, computed): `raw_score`, `z_score`, `t_score` (all
  Decimal), `cohort_size`, `cohort_key`, `insufficient_cohort` (bool),
  `risk_status` ∈ **ON_TRACK · AT_RISK · CRITICAL**, `pace_behind` (bool),
  `computed_at`.

## Reviews (Module 3)
- **Review** (`ReviewSerializer`): `employee`, `reviewer`, `cycle`,
  `state` ∈ **DRAFT · AI_DRAFTING · PENDING_HUMAN_REVIEW · EDITING · APPROVED ·
  REJECTED · FINALIZED**, `draft_body`, `final_body`, `human_reviewer` (null until
  approved), `approved_at`, `finalized_at`, `rejected_reason`,
  `source` ∈ **MANUAL · AI**, `confidence_score` (Decimal|null), `citations`
  (JSON|null), `approval_route` (UUID|null). State changes only via transition
  endpoints (no PATCH).
- **ReviewAssessment**: `assessment_type` ∈ **SELF · MANAGER · PEER · UPWARD**,
  `body`, `assessor`, `submitted_at`. Settable body; assessor server-set.
- **ReviewStateTransition** (read-only timeline): from/to state, action, actor, at.

## 360 Feedback (Module 4)
- **FeedbackCycle**: `subject`, `status` ∈ **DRAFT · COLLECTING · CLOSED**,
  `min_volume`, optional `performance_cycle`. Manage = Manager+.
- **FeedbackRequest** (the invitation): `relationship` ∈ **SELF · MANAGER · PEER ·
  UPWARD**, `status` ∈ **PENDING · SUBMITTED · DECLINED**, `giver`. Relationship is
  fixed by the inviter.
- **Feedback**: `body`, `relationship` ∈ same four, `kind` ∈ **THREE_SIXTY ·
  CONTINUOUS**, `giver_marked_sensitive` (bool). **`giver` is STORED but NEVER
  egressed** to recipients — the UI must not expect or render it on received/
  anonymised views.
- **Anonymised payload** (egress only): `subject_id` + items with opaque
  `pseudonym` (PEER#1…), `relationship`, `body`; `insufficient_groups` (list of
  groups below min volume — show as "too few responses"). NO giver identifiers.
- **FeedbackSummary**: `sections` (`{strengths, growth, themes, risks}` — **NULL
  until Agent 3 writes them; never fabricate**), `status` ∈ **PENDING_HUMAN_REVIEW ·
  HRBP_HOLD · APPROVED · RELEASED**, `anonymity_passed` (bool), `sensitive` (bool),
  `volume_total`, `confidence_score` (Decimal|null).
- **OneOnOneNote**: `body`, `meeting_date`, participants — visible to participants
  ONLY (even Admin denied); not anonymised, not summarised.

## Approvals (Module 5)
- **ApprovalWorkflow**: `name`, `artifact_type` (e.g. "review", "jd"),
  `mode` ∈ **SEQUENTIAL · PARALLEL**, `active` (bool). Config = HRBP/Admin.
- **ApprovalStep** (template): `order`, `approver_kind` ∈ **ROLE · NAMED**,
  `approver_role`, `approver_user`, `required` (bool), `timeout_hours`,
  `escalation_role`/`escalation_user`.
- **ApprovalRoute** (instance): `status` ∈ **IN_PROGRESS · APPROVED · REJECTED ·
  ESCALATED**, `mode`, `artifact_type`, `artifact_id`, `initiated_by`.
- **ApprovalStepInstance**: `order`, `approver`, `approver_role`,
  `status` ∈ **PENDING · APPROVED · REJECTED · ESCALATED · SKIPPED**, `due_at`,
  `escalated` (bool), `decided_by`/`decided_at`, `comment`.

## JD Library (Module 6)
- **JobDescription**: `title`, `level`, `department`,
  `status` ∈ **DRAFT · PENDING_HUMAN_REVIEW · IN_REVIEW · PUBLISHED · ARCHIVED**,
  `source` ∈ **MANUAL · AI**, `current_version` (UUID|null), `created_by`,
  `approval_route` (UUID|null).
- **JDVersion**: `version_number`, `body` (`{summary, responsibilities[],
  must_haves[], nice_to_haves[]}`), `inputs_snapshot`, `confidence_score`/`citations`
  (AI only), `is_published`.
- **JDRequest**: `requested_by`, `title`, `level`, `notes`,
  `status` ∈ **OPEN · FULFILLED · DECLINED**.

## Org (Module 7)
- **Org tree node** (read-only, computed): user `id`, `email`, `role`,
  `headcount` (subtree, inclusive), `vacancies` (OPEN positions in subtree); plus
  `edges` + `roots`.
- **Position**: `title`, `reports_to` (User|null), `department`,
  `status` ∈ **OPEN · FILLED · CLOSED**, `filled_by` (User|null), `published_jd`
  (JD|null), `opened_at`, `filled_at`, `created_by`. Manage = HRBP/Admin.

## Succession (Module 8 — management-only)
- **CriticalRole**: `name`, `position` (Position|null), `incumbent` (User|null),
  `criticality` ∈ **HIGH · CRITICAL**, `knowledge_risk` ∈ **LOW · MEDIUM · HIGH**,
  `risk_notes`, `status` ∈ **ACTIVE · ARCHIVED**, `marked_by`.
- **BenchCandidate**: `candidate`, `readiness` ∈ **READY_NOW · READY_SOON ·
  DEVELOPING · NOT_READY**, `readiness_overridden` (bool), `notes`, `added_by`.
- **NineBoxPlacement**: `employee`, `cycle`, `performance_band` ∈ **LOW · MEDIUM ·
  HIGH** (derived), `potential_band` ∈ same (human-assigned), `box` (1–9),
  `assessed_by`/`assessed_at`.
- **SuccessionPlan**: `status` ∈ **DRAFT · PENDING_HUMAN_REVIEW · PUBLISHED**,
  `ranked_bench` (JSON), `coverage_status` ∈ **RED · AMBER · GREEN**, `red_flags`
  (JSON), `action_items` (JSON), `source` ∈ **DETERMINISTIC · AI**,
  `confidence_score` (Decimal|null), `generated_at`, `reviewed_by`, `published_at`.

## Career (Module 9)
- **TargetRoleSelection**: `employee`, `target_jd` | `target_position` (exactly
  one), `selected_by`, `selected_at`.
- **DevelopmentRoadmap**: `status` ∈ **DRAFT · ACTIVE · ARCHIVED**, `tiers`
  (`[{index, title, detail, basis}]`), `skill_gap` (`{current_performance_band,
  required_performance_band, performance_band_gap, weak_categories[]}` — **no
  succession data**), `source` ∈ **DETERMINISTIC · AI**, `advisory` (**always
  true**), `confidence_score` (Decimal|null), `generated_by`.
- **RoadmapProgress**: `tier_index`, `status` ∈ **NOT_STARTED · IN_PROGRESS · DONE**.

## Billing & entitlements (Modules 1 + 11)
- **Entitlement**: `seat_count` (int, independent), `feature_packs` (list of
  **STARTER · FULL_AI**), `unlocked_agents` (computed list), `tier_label` (display
  only — "Starter" / "Full AI"; NEVER used for gating).
- **feature-flags map**: `{feature: bool}` over `agent1, agent2, agent3, agent4,
  agent5, chat, jd_generator, career_roadmap`. **STARTER unlocks `agent2` + `chat`
  only; everything else (incl. `agent1`) is FULL_AI/premium.**
- **AgentBudget** (system, not a UI CRUD): `agent_code` (or "all"),
  `window` ∈ **DAILY · MONTHLY**, `limit`. **TokenLedger** (system meter): usage rows.

## Audit (Module 11)
- **AuditLog** (read-only, immutable): `id`, `actor`, `action` (e.g.
  "review.approved"), `target_type`, `target_id`, `justification`, `metadata`
  (JSON), `created_at`. Console response: `{count, next, previous, results[]}`.

## Integrations (Module 12)
- **TenantIntegration**: `kind` ∈ **JIRA · SLACK**, `enabled` (bool), `config`
  (non-secret JSON: base_url/email/project/channel/value_field…), `secret_ref`
  (the **NAME** of an env var holding the token — **never the token value**,
  never returned). Settable by Admin; the UI captures a secret-name, not a secret.
