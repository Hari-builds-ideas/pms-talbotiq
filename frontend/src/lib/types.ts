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
  /** Opaque challenge handle echoed back to /mfa/challenge (mock convenience). */
  challenge?: string;
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
  box: number;
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

export interface ChatResponse {
  status: "ok" | "blocked";
  intent: string;
  answer: string;
  data?: unknown;
}

export interface Nudge {
  employee: UUID;
  level: NudgeLevel;
  message: string;
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
