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
  approver_role: Role | null;
  status: StepStatus;
  due_at: ISODate | null;
  escalated: boolean;
  decided_by: UUID | null;
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
  step_instances: ApprovalStepInstance[];
}

export interface InboxItem {
  id: UUID;
  route: UUID;
  order: number;
  approver_role: Role | null;
  status: StepStatus;
  due_at: ISODate | null;
  artifact_type: string;
  artifact_id: UUID;
  escalated?: boolean;
}

// ---- Reviews ---------------------------------------------------------------

export interface Review {
  id: UUID;
  employee: UUID;
  reviewer: UUID;
  cycle: UUID;
  state: ReviewState;
  draft_body: string;
  final_body: string;
  human_reviewer: UUID | null;
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
  action: string;
  actor: UUID;
  at: ISODate;
}

export interface ReviewAssessment {
  id: UUID;
  assessment_type: "SELF" | "MANAGER" | "PEER" | "UPWARD";
  body: string;
  assessor: UUID;
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
  department: string;
  status: PositionStatus;
  filled_by: UUID | null;
  published_jd: UUID | null;
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
  readiness: Readiness;
  readiness_overridden: boolean;
  notes: string;
}

export interface NineBoxPlacement {
  id: UUID;
  employee: UUID;
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
  ranked_bench: Array<{ candidate: UUID; readiness: Readiness }>;
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
  actor: UUID;
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
