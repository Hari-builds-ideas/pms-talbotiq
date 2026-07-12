/**
 * Domain types — shapes mirror the backend serializers exactly
 * (see docs/frontend-contract/03_data_dictionary.md). All ids are UUID strings;
 * decimals are STRINGS (2dp display) — never parsed as float for round-trips.
 */
import type {
  ApprovalMode,
  Band,
  CoverageStatus,
  FeatureKey,
  FeaturePack,
  IntegrationKind,
  JdStatus,
  NudgeLevel,
  PlanStatus,
  PositionStatus,
  Readiness,
  ReviewState,
  RiskStatus,
  Role,
  RouteStatus,
  StepStatus,
} from "./enums";

// ---- Generic envelopes -----------------------------------------------------

/** The shared DRF pagination envelope. */
export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export type Decimal = string; // e.g. "55.0000"
export type UUID = string;
export type ISODate = string; // datetime or plain date

// ---- Identity --------------------------------------------------------------

export interface Me {
  id: UUID;
  email: string;
  display_name: string | null;
  display: string;
  role: Role;
  tenant_id?: UUID;
  tenant_name?: string;
  tenant_slug?: string;
  manager_id?: UUID | null;
  mfa_enabled: boolean;
  /** The caller's capability grants, computed server-side from the SAME matrix
   *  RBAC enforces (apps/rbac/matrix.py) — the client's single source of truth
   *  for hiding controls the role can't use. Absent → treat as no grants. */
  capabilities?: string[];
  /** Tenant branding hooks (PHASE2 L1.5) — present only when the plan includes
   *  custom_branding; null/absent → the default brand. */
  tenant_branding?: { logo_url?: string; primary_color?: string } | null;
}

// ── PHASE2 L1.1/L1.3 — self-service profile + sessions ──
export interface Profile {
  id: UUID;
  email: string;
  display_name: string | null;
  display: string;
  role: Role;
  manager_id?: UUID | null;
  phone: string;
  title: string;
  department: string;
  employee_id: string;
  timezone: string;
  language: string;
  preferences: Record<string, unknown>;
  mfa_enabled: boolean;
  has_photo: boolean;
}

export interface DeviceSessionRow {
  id: UUID;
  ip: string | null;
  user_agent: string;
  created_at: string;
  last_seen: string;
  current: boolean;
}

export interface LoginEventRow {
  event: string;
  ip: string | null;
  user_agent: string;
  created_at: string;
}

export interface ActivityRow {
  action: string;
  target_type: string;
  target_id: string | null;
  created_at: string;
}

export interface SubscriptionInfo {
  plan: string;
  status: string;
  features_active: boolean;
  employee_limit: number;
  plan_features: string[];
  packs: string[];
  trial_ends_at: string | null;
  current_period_end: string | null;
  plans: Record<string, { label: string; employee_limit: number; features: string[] }>;
}

export interface InvitationRow {
  id: UUID;
  email: string;
  role: Role;
  status: "PENDING" | "ACCEPTED" | "REVOKED";
  invited_by?: UUID;
  created_at?: string;
  invite_url: string | null;
}

export interface AdminUser {
  id: UUID;
  email: string;
  display_name: string | null;
  display: string;
  role: Role;
  manager: UUID | null;
  is_active: boolean;
  mfa_enabled: boolean;
}

export interface AdminUserStats {
  total: number;
  active: number;
  inactive: number;
  active_by_role: Partial<Record<Role, number>>;
}

export interface TenantConfig {
  id: UUID;
  settings: Record<string, unknown>;
  /** Optimistic-lock version (BUILD_4): echo back on save; a stale value → 409. */
  version: number;
}

export interface PerformanceCycle {
  id: UUID;
  name: string;
  start_date: ISODate;
  end_date: ISODate;
  status: "DRAFT" | "ACTIVE" | "CLOSED";
}

// ---- Auth ------------------------------------------------------------------

export interface TokenPair {
  access: string;
  refresh: string;
}

export interface LoginResponse extends Partial<TokenPair> {
  /** Present + true when the user must complete an MFA challenge. */
  mfa_required?: boolean;
  /** Signed, short-lived MFA handle (the REAL backend field) — echoed back to
   *  /auth/mfa/challenge as `mfa_token` together with the TOTP code. */
  mfa_token?: string;
}

// ---- Billing / entitlements ------------------------------------------------

export type FeatureFlags = Record<FeatureKey, boolean>;

export interface Entitlement {
  seat_count: number;
  feature_packs: FeaturePack[];
  unlocked_agents: string[];
  tier_label: string;
}

export interface UpgradePrompt {
  current_packs: FeaturePack[];
  tier_label: string;
  feature_flags: FeatureFlags;
  locked_features: FeatureKey[];
  upgrade: {
    pack: FeaturePack;
    would_unlock: FeatureKey[];
    note: string;
  };
}

// ---- Approvals -------------------------------------------------------------

export interface ApprovalStepTemplate {
  order: number;
  approver_kind: "ROLE" | "NAMED";
  approver_role?: Role | null;
  approver_user?: UUID | null;
  required: boolean;
  timeout_hours: number;
  escalation_role?: Role | null;
  escalation_user?: UUID | null;
}

export interface ApprovalWorkflow {
  id: UUID;
  name: string;
  artifact_type: string;
  mode: ApprovalMode;
  active: boolean;
  steps?: ApprovalStepTemplate[];
}

export interface ApprovalStepInstance {
  id?: UUID;
  order: number;
  approver: UUID | null;
  approver_name?: string | null;
  approver_role: Role | null;
  status: StepStatus;
  due_at: ISODate | null;
  escalated: boolean;
  decided_by: UUID | null;
  decided_by_name?: string | null;
  decided_at: ISODate | null;
  comment: string;
}

export interface ApprovalRoute {
  id: UUID;
  status: RouteStatus;
  mode: ApprovalMode;
  artifact_type: string;
  artifact_id: UUID;
  initiated_by: UUID;
  initiated_by_name?: string | null;
  step_instances: ApprovalStepInstance[];
}

export interface InboxItem {
  id: UUID;
  route: UUID;
  order: number;
  approver: UUID | null;
  approver_name?: string | null;
  approver_role: Role | null;
  status: StepStatus;
  due_at: ISODate | null;
  artifact_type: string;
  artifact_id: UUID;
  escalated?: boolean;
}

// ---- Async AI jobs ---------------------------------------------------------

export type AIJobStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "DEGRADED" | "FAILED";

/** The poll shape of an async AI run. The seam endpoints return one of these
 *  (202); the client polls `aiJobsApi.get(id)` until `status` is terminal, then
 *  re-fetches `target_id` (the artifact) on SUCCEEDED. */
export interface AIJob {
  id: UUID;
  status: AIJobStatus;
  agent_code: string;
  target_type: string;
  target_id: UUID | null;
  /** The artifact the run produced (set on SUCCEEDED). Equals target_id for
   *  mutate-in-place seams; the NEW artifact for create-new (succession/career). */
  result_id: UUID | null;
  confidence: number | null;
  error_code: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

// ---- Reviews ---------------------------------------------------------------

export interface Review {
  id: UUID;
  employee: UUID;
  employee_name?: string | null;
  reviewer: UUID;
  reviewer_name?: string | null;
  cycle: UUID;
  cycle_name?: string | null;
  state: ReviewState;
  draft_body: string;
  final_body: string;
  human_reviewer: UUID | null;
  human_reviewer_name?: string | null;
  approved_at: ISODate | null;
  finalized_at: ISODate | null;
  rejected_reason: string | null;
  source: "MANUAL" | "AI";
  confidence_score: Decimal | null;
  citations: unknown[] | null;
  approval_route: UUID | null;
}

export interface ReviewTransition {
  from_state: ReviewState;
  to_state: ReviewState;
  /** Free-text note recorded with the transition (serializer exposes `note`). */
  note: string;
  actor: UUID | null;
  actor_name?: string | null;
  at: ISODate;
}

export interface ReviewAssessment {
  id: UUID;
  assessment_type: "SELF" | "MANAGER" | "PEER" | "UPWARD";
  body: string;
  assessor: UUID;
  assessor_name?: string | null;
  submitted_at: ISODate | null;
}

export type ReviewCommentSection =
  | "SUMMARY"
  | "STRENGTHS"
  | "DEVELOPMENT"
  | "GOALS"
  | "RECOMMENDATIONS";

export interface ReviewComment {
  id: UUID;
  author: UUID;
  author_name?: string | null;
  section: ReviewCommentSection | null; // null = a general comment
  body: string;
  parent: UUID | null; // a reply points at its top-level parent
  created_at: ISODate;
  edited_at: ISODate | null;
}

// ---- JD --------------------------------------------------------------------

export interface JdBody {
  summary: string;
  responsibilities: string[];
  must_haves: string[];
  nice_to_haves: string[];
}

export interface JobDescription {
  id: UUID;
  title: string;
  level: string;
  department: string;
  status: JdStatus;
  source: "MANUAL" | "AI";
  current_version: UUID | null;
  created_by?: UUID;
  created_by_name?: string | null;
  approval_route: UUID | null;
}

export interface JdVersion {
  id?: UUID;
  version_number: number;
  body: JdBody;
  confidence_score: Decimal | null;
  citations: unknown[] | null;
  is_published: boolean;
}

export interface JdRequest {
  id: UUID;
  requested_by: UUID;
  requested_by_name?: string | null;
  title: string;
  level: string;
  notes: string;
  status: "OPEN" | "FULFILLED" | "DECLINED";
}

// ---- Org -------------------------------------------------------------------

export interface OrgNode {
  id: UUID;
  email: string;
  display: string;
  role: Role;
  headcount: number;
  vacancies: number;
  /** All direct-report ids (from the full tree) — present even when the children
   *  themselves aren't in the payload (lazy mode), so the client knows a node has
   *  children to expand. */
  direct_report_ids: UUID[];
}

/**
 * The wire shape of `GET /api/org/tree` (the backend authority): `nodes` is a
 * LIST of node objects, `edges` are `{from,to}` objects. The client normalizes
 * this into `OrgTree` (an id→node map + tuple edges) via `normalizeOrgTree` at
 * the API boundary — the tree components consume the normalized shape only.
 */
export interface RawOrgTree {
  roots: UUID[];
  nodes: OrgNode[];
  edges: Array<{ from: UUID | null; to: UUID }>;
}

export interface OrgTree {
  roots: UUID[];
  nodes: Record<UUID, OrgNode>;
  edges: Array<[UUID, UUID]>;
}

export interface PersonCard {
  id: UUID;
  email: string;
  display_name: string | null;
  display: string;
  role: Role;
  title: string;
  manager: { id: UUID; email: string; display: string } | null;
  direct_reports: number;
  filled_positions: Array<{
    id: UUID;
    title: string;
    department: string;
    published_jd: UUID | null;
  }>;
  published_jds: UUID[];
}

export interface Position {
  id: UUID;
  title: string;
  reports_to: UUID | null;
  reports_to_name?: string | null;
  department: string;
  status: PositionStatus;
  filled_by: UUID | null;
  filled_by_name?: string | null;
  published_jd: UUID | null;
  published_jd_title?: string | null;
  opened_at: ISODate | null;
  filled_at: ISODate | null;
}

export interface PersonRef {
  id: UUID;
  email: string;
  display_name?: string | null;
  display: string;
  role: Role;
  title?: string;
}

// ---- Succession ------------------------------------------------------------

export interface CriticalRoleSummary {
  id: UUID;
  name: string;
  criticality: "HIGH" | "CRITICAL";
  knowledge_risk: "LOW" | "MEDIUM" | "HIGH";
  status: "ACTIVE" | "ARCHIVED";
  coverage_status: CoverageStatus;
  published_plan: UUID | null;
}

export interface SuccessionDashboard {
  critical_roles: CriticalRoleSummary[];
}

export interface CriticalRole {
  id: UUID;
  name: string;
  position: UUID | null;
  incumbent: UUID | null;
  incumbent_name?: string | null;
  criticality: "HIGH" | "CRITICAL";
  knowledge_risk: "LOW" | "MEDIUM" | "HIGH";
  risk_notes: string;
  status: "ACTIVE" | "ARCHIVED";
  coverage_status?: CoverageStatus;
  published_plan?: UUID | null;
}

export interface BenchCandidate {
  id: UUID;
  candidate: UUID;
  candidate_name?: string | null;
  readiness: Readiness;
  readiness_overridden: boolean;
  notes: string;
}

export interface NineBoxPlacement {
  id: UUID;
  employee: UUID;
  employee_name?: string | null;
  cycle: UUID;
  performance_band: Band;
  potential_band: Band;
  box: number; // the computed cell (never rewritten by an override)
  override_box: number | null; // a human override of the cell, or null
  override_by?: UUID | null;
  override_at?: ISODate | null;
  override_rationale?: string;
  effective_box: number; // override_box ?? box — the cell to display
  is_overridden: boolean;
}

export interface SuccessionPlan {
  id: UUID;
  status: PlanStatus;
  coverage_status: CoverageStatus;
  source: "DETERMINISTIC" | "AI";
  confidence_score: Decimal | null;
  ranked_bench: Array<{
    candidate_id: UUID;
    candidate_email?: string;
    candidate_name?: string | null;
    readiness: Readiness;
    performance_band?: Band;
  }>;
  red_flags: Array<string | { code?: string; detail?: string }>;
  action_items: Array<{ text: string; added_by?: UUID }>;
}

// ---- Analytics -------------------------------------------------------------

export interface IndividualTrendPoint {
  cycle: UUID;
  t_score: Decimal;
  risk_status: RiskStatus;
  raw_score: Decimal;
  pace_behind: boolean;
}

export interface IndividualAnalytics {
  employee: UUID;
  trend: IndividualTrendPoint[];
}

export interface DepartmentAnalytics {
  head: UUID;
  cycle: UUID;
  cohort_size: number;
  min_cohort: number;
  suppressed: boolean;
  aggregate: {
    headcount: number;
    scored: number;
    mean_t_score: number;
    median_t_score: number;
    risk_distribution: Record<RiskStatus, number>;
  };
  individuals: Array<{ employee: UUID; t_score: Decimal; risk_status: RiskStatus }>;
  note?: string;
}

export interface CalibrationGrid {
  cycle: UUID;
  total: number;
  grid: Record<string, number>;
  placements: Array<{
    employee: UUID;
    box: number;
    performance_band: Band;
    potential_band: Band;
  }>;
}

// ---- Audit -----------------------------------------------------------------

export interface AuditLog {
  id: UUID;
  actor: UUID | null;
  actor_name?: string | null;
  action: string;
  target_type: string;
  target_id: UUID;
  justification: string;
  metadata: Record<string, unknown>;
  created_at: ISODate;
}

// ---- Integrations ----------------------------------------------------------

export interface TenantIntegration {
  id: UUID;
  kind: IntegrationKind;
  enabled: boolean;
  config: Record<string, unknown>;
  secret_ref: string;
}

// ---- AI --------------------------------------------------------------------

/** A proposed assistant action — inert until the human acts (RW_BUILD_4 / AGENTIC_CHAT).
 *  feel decides HOW the human completes it:
 *   - "confirm"  → tap Approve → aiApi.executeAction (server re-checks permission + scope);
 *   - "navigate" → open `deeplink` (with `prefill`) and complete it on that screen's own
 *     audited endpoint (the chat never writes for these);
 *   - "clarify"  → the summary is a question; no action until the user rephrases. */
export interface ChatProposal {
  action: string;
  summary: string;
  preview: Record<string, unknown>[];
  params?: Record<string, unknown>;
  feel?: "confirm" | "navigate" | "clarify";
  deeplink?: string;
  prefill?: Record<string, unknown>;
}
export interface ChatActionResult {
  action: string;
  approved?: number;
  // Skipped targets carry a reason; the id key depends on the action.
  skipped?: { reason: string; goal_id?: string; review_id?: string }[];
  // AGENTIC_CHAT confirm results (enqueue / create) carry a human message + ref.
  ok?: boolean;
  message?: string;
  job_id?: string;
  cycle_id?: string;
}
export interface ChatResponse {
  /** AGENT_UX_V3 §A — a write now returns "plan"; reads stay ok/blocked. */
  status: "ok" | "blocked" | "proposal" | "plan";
  intent: string;
  answer: string;
  data?: unknown;
  proposal?: ChatProposal;
  /** Present when status === "plan": the ordered, inert plan to approve step by step. */
  type?: "plan";
  plan?: ChatPlan;
  /** The chat session id — threaded back on the next message for short-term memory. */
  session_id?: UUID;
}

/** Agentic chat V2 (OVERNIGHT_A) — a plan is an ordered, INERT checklist the human
 *  approves step by step. Nothing runs until a per-step Approve; each step then
 *  executes through the same audited, RBAC/scope-checked gate as the human UI. */
export interface ChatPlanStep {
  id: UUID;
  ordinal: number;
  action: string;
  feel: "confirm" | "navigate" | "clarify";
  summary: string;
  /** The grounded "why", composed server-side from real fetched facts. */
  reason: string;
  preview: Record<string, unknown>[];
  deeplink?: string;
  prefill?: Record<string, unknown>;
  candidates?: Record<string, unknown>[];
  status: "pending" | "approved" | "done" | "skipped" | "failed";
  result?: Record<string, unknown>;
}
export interface ChatPlan {
  id: UUID;
  session: UUID;
  message: string;
  summary: string;
  confidence?: number | null;
  steps: ChatPlanStep[];
  created_at: string;
}
export interface ChatPlanResponse {
  session_id: UUID;
  plan: ChatPlan;
}
/** Result of approving ONE step. Idempotent; `out_of_order` flags approving ahead
 *  of still-pending earlier steps (earlier steps are never auto-run). */
export interface ChatStepApproveResult {
  plan_id: UUID;
  step_id: UUID;
  action: string;
  feel: string;
  ordinal: number;
  out_of_order: boolean;
  idempotent?: boolean;
  status: "done" | "in_progress" | "skipped" | "needs_clarification" | "failed";
  result?: Record<string, unknown>;
  deeplink?: string;
  prefill?: Record<string, unknown>;
  question?: string;
  candidates?: Record<string, unknown>[];
}
export interface ChatTurn {
  id: UUID;
  role: "user" | "assistant";
  text: string;
  refs: Record<string, unknown>[];
  created_at: string;
}
export interface ChatSessionSummary {
  id: UUID;
  title: string;
  last_activity: string;
  created_at: string;
}
export interface ChatSessionDetail extends ChatSessionSummary {
  turns: ChatTurn[];
}

export interface Nudge {
  employee: UUID;
  level: NudgeLevel;
  message: string;
}

/** RW_BUILD_5 quick win — a stateless AI summary of 1-on-1 / meeting notes.
 *  DRAFT only: the server persists nothing; the manager keeps/uses the result. */
export interface MeetingSummary {
  summary: string;
  action_items: string[];
}
export interface MeetingSummaryResponse {
  status: "ok";
  summary: MeetingSummary;
  confidence?: number;
}

/** RW_BUILD_5 quick win — an ADVISORY quality/bias flag on a draft review's text.
 *  type ∈ recency_bias | harsh_wording | missing_evidence | vague | other. Never
 *  blocks; persists nothing. An empty list means the text reads clean. */
export interface ReviewQualityFlag {
  type: string;
  note: string;
}
export interface ReviewQualityResponse {
  status: "ok";
  flags: ReviewQualityFlag[];
  confidence?: number;
}

/** RW_BUILD_5 quick win — a manager's ACTIVE goals with no KPI progress in ~30 days
 *  (deterministic, scope-bound) plus ONE advisory AI follow-up suggestion. READ-ONLY;
 *  the list always returns, the suggestion is null when the AI is unavailable. */
export interface StaleGoal {
  goal: string;
  employee: string;
  days_stale: number | null;
}
export interface StaleGoalsResponse {
  stale: StaleGoal[];
  suggestion: string | null;
}

// ---- Goals & KPIs (Module 2) -----------------------------------------------

export interface Kpi {
  id: UUID;
  name: string;
  description?: string;
  weight: Decimal;
  target_value: Decimal;
  direction: "INCREASING" | "DECREASING";
  unit: string;
  source: "MANUAL" | "JIRA";
  external_ref?: string | null;
  latest_actual?: Decimal | null;
}

/** A goal's progress-timeline entry (AGENT_UX_V3 Part 2.3). */
export interface GoalUpdate {
  id: UUID;
  goal: UUID;
  text: string;
  author: UUID | null;
  author_name: string | null;
  created_at: string;
}

export interface Goal {
  id: UUID;
  employee: UUID;
  employee_name?: string | null;
  cycle: UUID;
  created_by: UUID;
  created_by_name?: string | null;
  title: string;
  description: string;
  objective: string;
  weight: Decimal;
  status: "DRAFT" | "ACTIVE" | "ACHIEVED" | "MISSED" | "ARCHIVED";
  approved_by: UUID | null;
  approved_by_name?: string | null;
  approved_at: ISODate | null;
  kpis: Kpi[];
  kpi_weight_total?: Decimal;
  /** Optimistic-lock version (BUILD_4): echo back on a plain-field PATCH; stale → 409. */
  version: number;
}

export interface CycleScore {
  id?: UUID;
  employee: UUID;
  cycle: UUID;
  raw_score: Decimal;
  z_score: Decimal;
  t_score: Decimal;
  cohort_size: number;
  insufficient_cohort: boolean;
  risk_status: "ON_TRACK" | "AT_RISK" | "CRITICAL";
  pace_behind: boolean;
  computed_at: ISODate;
}

// ---- 360 Feedback (Module 4) -----------------------------------------------

export type FeedbackRelationship = "SELF" | "MANAGER" | "PEER" | "UPWARD";

export interface FeedbackCycle {
  id: UUID;
  subject: UUID;
  subject_name?: string | null;
  status: "DRAFT" | "COLLECTING" | "CLOSED";
  opened_at: ISODate | null;
  closed_at: ISODate | null;
  min_volume: number | null;
  performance_cycle: UUID | null;
}

/**
 * A cycle ABOUT the caller, returned by `GET /feedback/my-cycles` — the
 * subject's own discovery shape. Extends the public cycle with just enough
 * summary metadata to decide whether to fetch the released summary; the
 * content itself stays gated behind `/cycles/<id>/summary` (RELEASED-only).
 */
export interface MyFeedbackCycle extends FeedbackCycle {
  summary_id: UUID | null;
  summary_status: FeedbackSummary["status"] | null;
  summary_released: boolean;
}

export interface FeedbackRequestItem {
  id: UUID;
  cycle: UUID;
  giver: UUID;
  giver_name?: string | null;
  relationship: FeedbackRelationship;
  status: "PENDING" | "SUBMITTED" | "DECLINED";
}

export interface OwnFeedback {
  id: UUID;
  cycle: UUID | null;
  subject: UUID;
  relationship: FeedbackRelationship;
  kind: "THREE_SIXTY" | "CONTINUOUS";
  body: string;
  giver_marked_sensitive: boolean;
  created_at: ISODate;
}

export interface FeedbackSummary {
  id: UUID;
  cycle: UUID;
  subject: UUID;
  subject_name?: string | null;
  sections: {
    strengths?: string;
    growth?: string;
    themes?: string;
    risks?: string;
  } | null;
  status: "PENDING_HUMAN_REVIEW" | "HRBP_HOLD" | "APPROVED" | "RELEASED";
  anonymity_passed: boolean;
  sensitive: boolean;
  volume_total: number;
  insufficient_groups: string[];
  insufficient_volume: boolean;
  confidence_score: Decimal | null;
  generated_at: ISODate | null;
  released_at: ISODate | null;
}

/** Result of close/summarize (the Agent-3 pipeline outcome). */
export interface FeedbackSummarizeResult {
  summarized: boolean;
  reason?: string; // not_found | anonymity_breach | no_provider | sensitive | …
  summary_id?: UUID;
  status?: string;
  detail?: string;
}

/** The ONLY 360 egress artifact — giver-stripped, pseudonymised, volume-gated. */
export interface AnonymizedGroupItem {
  pseudonym: string;
  body: string;
  marked_sensitive: boolean;
}
export interface AnonymizedPayload {
  cycle_id: UUID;
  subject_id: UUID;
  min_volume: number;
  volumes: Record<FeedbackRelationship, number>;
  insufficient_groups: FeedbackRelationship[];
  insufficient_volume: boolean;
  groups: Partial<Record<FeedbackRelationship, AnonymizedGroupItem[]>>;
}

// ---- Career (Module 9) -----------------------------------------------------

export interface RoadmapTier {
  index: number;
  title: string;
  detail: string;
  basis: string;
}

export interface WeakCategory {
  goal: string;
  goal_id: UUID;
  raw_score: string;
}

export interface SkillGap {
  current_performance_band?: string;
  required_performance_band?: string;
  performance_band_gap?: number;
  weak_categories?: WeakCategory[];
}

export interface DevelopmentRoadmap {
  id: UUID;
  employee: UUID;
  employee_name?: string | null;
  status: "DRAFT" | "ACTIVE" | "ARCHIVED";
  target_jd: UUID | null;
  target_jd_title?: string | null;
  target_position: UUID | null;
  target_position_title?: string | null;
  selection: UUID | null;
  tiers: RoadmapTier[];
  skill_gap: SkillGap | null;
  source: "DETERMINISTIC" | "AI";
  advisory: boolean;
  confidence_score: Decimal | null;
  generated_at: ISODate;
  generated_by: UUID | null;
}

export type RoadmapProgressStatus = "NOT_STARTED" | "IN_PROGRESS" | "DONE";

export interface RoadmapProgressItem {
  id: UUID;
  roadmap: UUID;
  tier_index: number;
  status: RoadmapProgressStatus;
  updated_by: UUID | null;
}

export interface TargetRoleSelection {
  id: UUID;
  employee: UUID;
  target_jd: UUID | null;
  target_position: UUID | null;
  selected_by: UUID | null;
  selected_at: ISODate;
}

/** `POST /career/target` result: the selection + its freshly-generated roadmap. */
export interface TargetSelectResult {
  selection: TargetRoleSelection;
  roadmap: DevelopmentRoadmap;
}

/** `POST /career/roadmaps/<id>/enrich` body (the AI seam). On success
 * `{generated:true, roadmap_id, status}`; the no-provider seam is a 503 with
 * `{generated:false, reason:"no_provider", detail}`; other skips are 409. */
export interface RoadmapEnrichResult {
  generated: boolean;
  reason?: string;
  detail?: string;
  roadmap_id?: UUID;
  status?: DevelopmentRoadmap["status"];
}

// ── RW_BUILD_2 — Recognition (kudos) ──────────────────────────────────────────
export type RecognitionVisibility = "PRIVATE" | "MANAGER_ONLY" | "TEAM" | "COMPANY";
export interface RecognitionPerson {
  id: UUID;
  display: string;
}
export interface RecognitionReactions {
  /** emoji -> count */
  counts: Record<string, number>;
  /** the emojis the viewer has reacted with */
  mine: string[];
}
export interface RecognitionCard {
  id: UUID;
  sender: RecognitionPerson;
  recipient: RecognitionPerson;
  value: string;
  message: string;
  badge: string;
  visibility: RecognitionVisibility;
  created_at: string;
  reactions: RecognitionReactions;
  /** true iff the viewer is the sender (only the sender may remove it) */
  can_delete: boolean;
}
export interface RecognitionMeta {
  values: string[];
  reactions: string[];
  visibilities: { value: RecognitionVisibility; label: string }[];
}
export interface RecognitionAnalytics {
  total: number;
  top_values: { value: string; count: number }[];
  by_visibility: Record<string, number>;
  you: { given: number; received: number };
}

// ── RW_BUILD_3 — Weekly Check-ins ─────────────────────────────────────────────
export type CheckInPriorityStatus = "ACTIVE" | "DONE" | "CARRY_FORWARD";
export interface CheckInPerson {
  id: UUID;
  display: string;
}
export interface CheckInPriority {
  id: UUID;
  text: string;
  status: CheckInPriorityStatus;
}
export interface CheckInManagerResponse {
  comment: string;
  reaction: string;
  follow_up: boolean;
  add_to_one_on_one: boolean;
  responder: CheckInPerson;
}
export interface CheckInGoalProgress {
  goal: string;
  attainment_pct: number | null;
}
export interface CheckIn {
  id: UUID;
  author: CheckInPerson;
  week_of: string;
  mood: number;
  wins: string;
  blockers: string;
  learning: string;
  priorities: CheckInPriority[];
  response: CheckInManagerResponse | null;
  created_at: string;
  /** present on the detail endpoint — read-only pull from the goals engine */
  goal_progress?: CheckInGoalProgress[];
}

// ── RW_BUILD_5 — AI goal-writer (draft, never auto-saved) ─────────────────────
export interface GoalDraftKpi {
  name: string;
  target_value: string;
  unit: string;
  direction: string;
}
export interface GoalDraft {
  title: string;
  objective: string;
  kpis: GoalDraftKpi[];
}
export interface GoalDraftResponse {
  status: string;
  draft: GoalDraft;
  confidence?: number;
}
