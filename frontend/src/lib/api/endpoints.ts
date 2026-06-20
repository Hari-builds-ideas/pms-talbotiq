import { api } from "./client";
import type {
  AdminUser,
  AdminUserStats,
  ApprovalRoute,
  ApprovalWorkflow,
  AnonymizedPayload,
  AuditLog,
  BenchCandidate,
  CalibrationGrid,
  ChatResponse,
  CriticalRole,
  CycleScore,
  DevelopmentRoadmap,
  SkillGap,
  RoadmapProgressItem,
  RoadmapProgressStatus,
  TargetSelectResult,
  RoadmapEnrichResult,
  FeedbackCycle,
  FeedbackRequestItem,
  FeedbackSummarizeResult,
  FeedbackSummary,
  MyFeedbackCycle,
  Goal,
  OwnFeedback,
  DepartmentAnalytics,
  Entitlement,
  FeatureFlags,
  IndividualAnalytics,
  InboxItem,
  JdRequest,
  JdVersion,
  JobDescription,
  Me,
  NineBoxPlacement,
  Nudge,
  OrgTree,
  Paginated,
  PerformanceCycle,
  PersonCard,
  PersonRef,
  Position,
  Review,
  ReviewAssessment,
  ReviewTransition,
  SuccessionDashboard,
  SuccessionPlan,
  TenantConfig,
  TenantIntegration,
  TokenPair,
  UpgradePrompt,
} from "@/lib/types";
import type {
  FeaturePack,
  IntegrationKind,
  Readiness,
  Role,
} from "@/lib/enums";

/**
 * Typed API surface. Every function maps 1:1 to a contract endpoint. These run
 * against MSW (mocks) or the live backend transparently — the toggle is the
 * env flag wired in main.tsx; the functions never change.
 */

async function unwrap<T>(p: Promise<{ data: T }>): Promise<T> {
  return (await p).data;
}

export interface PageParams {
  page?: number;
  page_size?: number;
}

// ---- Auth ------------------------------------------------------------------

export const authApi = {
  login: (body: { email: string; password: string; tenant_slug: string }) =>
    unwrap<import("@/lib/types").LoginResponse>(api.post("/auth/login", body)),
  mfaChallenge: (body: { challenge?: string; code: string }) =>
    unwrap<TokenPair>(api.post("/auth/mfa/challenge", body)),
  mfaEnroll: () =>
    unwrap<{ secret: string; otpauth_url: string }>(api.post("/auth/mfa/enroll", {})),
  mfaEnrollConfirm: (body: { code: string }) =>
    unwrap<{ ok: boolean }>(api.post("/auth/mfa/enroll/confirm", body)),
  me: () => unwrap<Me>(api.get("/auth/me")),
  logout: () => unwrap<unknown>(api.post("/auth/logout", {})),
};

// ---- Billing ---------------------------------------------------------------

export const billingApi = {
  myFeatures: () => unwrap<FeatureFlags>(api.get("/billing/my-features")),
  featureFlags: () => unwrap<FeatureFlags>(api.get("/billing/feature-flags")),
  entitlement: () => unwrap<Entitlement>(api.get("/billing/entitlement")),
  upgradePrompt: () => unwrap<UpgradePrompt>(api.get("/billing/upgrade-prompt")),
  upgrade: (body: { pack: FeaturePack }) =>
    unwrap<Entitlement>(api.post("/billing/upgrade", body)),
  setSeats: (body: { seat_count: number }) =>
    unwrap<Entitlement>(api.patch("/billing/seats", body)),
};

// ---- Admin -----------------------------------------------------------------

export const adminApi = {
  users: () => unwrap<AdminUser[]>(api.get("/admin/users")),
  userStats: () => unwrap<AdminUserStats>(api.get("/admin/users/stats")),
  createUser: (body: {
    email: string;
    role: Role;
    manager?: string | null;
    display_name?: string | null;
    password?: string;
  }) => unwrap<AdminUser>(api.post("/admin/users", body)),
  setRole: (id: string, role: Role) =>
    unwrap<AdminUser>(api.post(`/admin/users/${id}/role`, { role })),
  deactivate: (id: string) =>
    unwrap<AdminUser>(api.post(`/admin/users/${id}/deactivate`, {})),
  reactivate: (id: string) =>
    unwrap<AdminUser>(api.post(`/admin/users/${id}/reactivate`, {})),
  setReportingLine: (id: string, manager: string | null) =>
    unwrap<AdminUser>(api.post(`/admin/users/${id}/reporting-line`, { manager })),
  setDisplayName: (id: string, display_name: string | null) =>
    unwrap<AdminUser>(api.post(`/admin/users/${id}/display-name`, { display_name })),
  tenantConfig: () => unwrap<TenantConfig>(api.get("/admin/tenant-config")),
  saveTenantConfig: (settings: Record<string, unknown>) =>
    unwrap<TenantConfig>(api.put("/admin/tenant-config", { settings })),
};

// ---- Approvals -------------------------------------------------------------

export const approvalsApi = {
  inbox: () => unwrap<InboxItem[]>(api.get("/approvals/inbox")),
  workflows: () => unwrap<ApprovalWorkflow[]>(api.get("/approvals/workflows")),
  createWorkflow: (body: Partial<ApprovalWorkflow>) =>
    unwrap<ApprovalWorkflow>(api.post("/approvals/workflows", body)),
  activateWorkflow: (id: string) =>
    unwrap<ApprovalWorkflow>(api.post(`/approvals/workflows/${id}/activate`, {})),
  deactivateWorkflow: (id: string) =>
    unwrap<ApprovalWorkflow>(api.post(`/approvals/workflows/${id}/deactivate`, {})),
  route: (id: string) => unwrap<ApprovalRoute>(api.get(`/approvals/routes/${id}`)),
  routesFor: (artifact_type: string, artifact_id: string) =>
    unwrap<ApprovalRoute[]>(
      api.get("/approvals/routes", { params: { artifact_type, artifact_id } }),
    ),
  approveStep: (id: string, comment?: string) =>
    unwrap<ApprovalRoute>(api.post(`/approvals/steps/${id}/approve`, { comment })),
  rejectStep: (id: string, comment: string) =>
    unwrap<ApprovalRoute>(api.post(`/approvals/steps/${id}/reject`, { comment })),
};

// ---- Cycles ----------------------------------------------------------------

export const cyclesApi = {
  list: () => unwrap<PerformanceCycle[]>(api.get("/cycles/")),
  scores: (cycleId: string) =>
    unwrap<CycleScore[]>(api.get(`/cycles/${cycleId}/scores`)),
  myScore: (cycleId: string) =>
    unwrap<CycleScore | null>(api.get(`/cycles/${cycleId}/scores/me`)),
  recompute: (cycleId: string) =>
    unwrap<unknown>(api.post(`/cycles/${cycleId}/recompute`, {})),
};

// ---- Reviews ---------------------------------------------------------------

export const reviewsApi = {
  list: (params: PageParams & { cycle?: string; state?: string; employee?: string } = {}) =>
    unwrap<Paginated<Review>>(api.get("/reviews/", { params })),
  create: (body: { employee: string; cycle: string }) =>
    unwrap<Review>(api.post("/reviews/", body)),
  upsertAssessment: (id: string, body: { assessment_type: string; body: string }) =>
    unwrap<ReviewAssessment>(api.post(`/reviews/${id}/assessments`, body)),
  detail: (id: string) => unwrap<Review>(api.get(`/reviews/${id}`)),
  timeline: (id: string) =>
    unwrap<ReviewTransition[]>(api.get(`/reviews/${id}/timeline`)),
  assessments: (id: string) =>
    unwrap<ReviewAssessment[]>(api.get(`/reviews/${id}/assessments`)),
  startEdit: (id: string) =>
    unwrap<Review>(api.post(`/reviews/${id}/start-edit`, {})),
  submit: (id: string, draft_body: string) =>
    unwrap<Review>(api.post(`/reviews/${id}/submit`, { draft_body })),
  saveDraft: (id: string, draft_body: string) =>
    unwrap<Review>(api.post(`/reviews/${id}/save-draft`, { draft_body })),
  approve: (id: string) => unwrap<Review>(api.post(`/reviews/${id}/approve`, {})),
  reject: (id: string, reason: string) =>
    unwrap<Review>(api.post(`/reviews/${id}/reject`, { reason })),
  finalize: (id: string) =>
    unwrap<Review>(api.post(`/reviews/${id}/finalize`, {})),
  requestAiDraft: (id: string) =>
    unwrap<Review>(api.post(`/reviews/${id}/request-ai-draft`, {})),
};

// ---- JD --------------------------------------------------------------------

export const jdApi = {
  list: (params: PageParams & { status?: string; q?: string } = {}) =>
    unwrap<Paginated<JobDescription>>(api.get("/jd/", { params })),
  create: (body: { title: string; level: string; department: string }) =>
    unwrap<JobDescription>(api.post("/jd/", body)),
  detail: (id: string) => unwrap<JobDescription>(api.get(`/jd/${id}`)),
  versions: (id: string) => unwrap<JdVersion[]>(api.get(`/jd/${id}/versions`)),
  saveDraft: (id: string, body: JdVersion["body"]) =>
    unwrap<JobDescription>(api.post(`/jd/${id}/save-draft`, { body })),
  saveInputs: (id: string, inputs: Record<string, unknown>) =>
    unwrap<JobDescription>(api.post(`/jd/${id}/save-draft`, { inputs })),
  submit: (id: string) => unwrap<JobDescription>(api.post(`/jd/${id}/submit`, {})),
  approve: (id: string) => unwrap<JobDescription>(api.post(`/jd/${id}/approve`, {})),
  revise: (id: string) => unwrap<JobDescription>(api.post(`/jd/${id}/revise`, {})),
  archive: (id: string) => unwrap<JobDescription>(api.post(`/jd/${id}/archive`, {})),
  generate: (id: string, body: { prompt?: string }) =>
    unwrap<JobDescription>(api.post(`/jd/${id}/generate`, body)),
  requests: (params: PageParams = {}) =>
    unwrap<Paginated<JdRequest>>(api.get("/jd/requests", { params })),
  createRequest: (body: { title: string; level: string; notes: string }) =>
    unwrap<JdRequest>(api.post("/jd/requests", body)),
  fulfilRequest: (id: string) =>
    unwrap<JdRequest>(api.post(`/jd/requests/${id}/fulfil`, {})),
  declineRequest: (id: string) =>
    unwrap<JdRequest>(api.post(`/jd/requests/${id}/decline`, {})),
};

// ---- Org -------------------------------------------------------------------

export const orgApi = {
  tree: () => unwrap<OrgTree>(api.get("/org/tree")),
  person: (id: string) => unwrap<PersonCard>(api.get(`/org/people/${id}`)),
  search: (q: string, params: PageParams = {}) =>
    unwrap<Paginated<PersonRef>>(api.get("/org/search", { params: { q, ...params } })),
  vacancies: () => unwrap<Position[]>(api.get("/org/vacancies")),
  positions: (params: PageParams = {}) =>
    unwrap<Paginated<Position>>(api.get("/org/positions", { params })),
  createPosition: (body: {
    title: string;
    reports_to: string | null;
    department: string;
  }) => unwrap<Position>(api.post("/org/positions", body)),
  fillPosition: (id: string, filled_by: string) =>
    unwrap<Position>(api.post(`/org/positions/${id}/fill`, { filled_by })),
  closePosition: (id: string) =>
    unwrap<Position>(api.post(`/org/positions/${id}/close`, {})),
  linkJd: (id: string, jd: string) =>
    unwrap<Position>(api.post(`/org/positions/${id}/link-jd`, { jd })),
  unlinkJd: (id: string) =>
    unwrap<Position>(api.post(`/org/positions/${id}/unlink-jd`, {})),
  reassign: (employee: string, manager: string | null) =>
    unwrap<{ ok: boolean }>(
      api.post("/org/reassign", { user: employee, new_manager: manager }),
    ),
};

// ---- Succession ------------------------------------------------------------

export const successionApi = {
  dashboard: () => unwrap<SuccessionDashboard>(api.get("/succession/dashboard")),
  criticalRoles: (params: PageParams = {}) =>
    unwrap<Paginated<CriticalRole>>(api.get("/succession/critical-roles", { params })),
  createCriticalRole: (body: Partial<CriticalRole>) =>
    unwrap<CriticalRole>(api.post("/succession/critical-roles", body)),
  setKnowledgeRisk: (id: string, knowledge_risk: string, risk_notes?: string) =>
    unwrap<CriticalRole>(
      api.post(`/succession/critical-roles/${id}/knowledge-risk`, {
        knowledge_risk,
        risk_notes,
      }),
    ),
  archiveCriticalRole: (id: string) =>
    unwrap<CriticalRole>(api.post(`/succession/critical-roles/${id}/archive`, {})),
  bench: (roleId: string, params: PageParams = {}) =>
    unwrap<Paginated<BenchCandidate>>(
      api.get(`/succession/critical-roles/${roleId}/bench`, { params }),
    ),
  addBench: (roleId: string, body: { candidate: string; notes?: string }) =>
    unwrap<BenchCandidate>(
      api.post(`/succession/critical-roles/${roleId}/bench`, body),
    ),
  setReadiness: (benchId: string, readiness: Readiness) =>
    unwrap<BenchCandidate>(
      api.post(`/succession/bench/${benchId}/readiness`, { readiness }),
    ),
  generate: (roleId: string) =>
    unwrap<SuccessionPlan>(
      api.post(`/succession/critical-roles/${roleId}/generate`, {}),
    ),
  nineBox: (params: PageParams & { cycle?: string } = {}) =>
    unwrap<Paginated<NineBoxPlacement>>(api.get("/succession/nine-box", { params })),
  assessNineBox: (body: {
    employee: string;
    cycle: string;
    potential_band: string;
  }) => unwrap<NineBoxPlacement>(api.post("/succession/nine-box", body)),
  plan: (id: string) => unwrap<SuccessionPlan>(api.get(`/succession/plans/${id}`)),
  addActionItem: (id: string, text: string) =>
    unwrap<SuccessionPlan>(api.post(`/succession/plans/${id}/action-item`, { text })),
  publishPlan: (id: string) =>
    unwrap<SuccessionPlan>(api.post(`/succession/plans/${id}/publish`, {})),
  enrichPlan: (id: string) =>
    unwrap<{ enriched: boolean; plan_id: string; status: string }>(
      api.post(`/succession/plans/${id}/enrich`, {}),
    ),
};

// ---- Analytics -------------------------------------------------------------

export const analyticsApi = {
  individual: (employee?: string) =>
    unwrap<IndividualAnalytics>(
      api.get("/analytics/individual", { params: employee ? { employee } : {} }),
    ),
  department: (head: string, cycle: string) =>
    unwrap<DepartmentAnalytics>(
      api.get("/analytics/department", { params: { head, cycle } }),
    ),
  calibration: (cycle: string) =>
    unwrap<CalibrationGrid>(api.get("/analytics/calibration", { params: { cycle } })),
};

// ---- Audit -----------------------------------------------------------------

export interface AuditFilters extends PageParams {
  actor?: string;
  action?: string;
  target_type?: string;
  target_id?: string;
  date_from?: string;
  date_to?: string;
}

export const auditApi = {
  logs: (params: AuditFilters = {}) =>
    unwrap<Paginated<AuditLog>>(api.get("/audit/logs", { params })),
};

// ---- Integrations ----------------------------------------------------------

export const integrationsApi = {
  list: () => unwrap<TenantIntegration[]>(api.get("/integrations/")),
  detail: (kind: IntegrationKind) =>
    unwrap<TenantIntegration>(api.get(`/integrations/${kind}`)),
  save: (
    kind: IntegrationKind,
    body: { enabled: boolean; config: Record<string, unknown>; secret_ref: string },
  ) => unwrap<TenantIntegration>(api.put(`/integrations/${kind}`, body)),
};

// ---- AI --------------------------------------------------------------------

export const aiApi = {
  chat: (query: string) => unwrap<ChatResponse>(api.post("/ai/chat", { query })),
  nudges: () => unwrap<Nudge[]>(api.get("/ai/nudges")),
};

// ---- Goals & KPIs ----------------------------------------------------------

export const goalsApi = {
  list: (params: PageParams & { employee?: string; cycle?: string } = {}) =>
    unwrap<Paginated<Goal>>(api.get("/goals/", { params })),
  detail: (id: string) => unwrap<Goal>(api.get(`/goals/${id}`)),
  create: (body: {
    employee: string;
    cycle: string;
    title: string;
    description?: string;
    objective?: string;
    weight: string;
    kpis: Array<{
      name: string;
      description?: string;
      weight: string;
      target_value: string;
      direction: string;
      unit?: string;
    }>;
  }) => unwrap<Goal>(api.post("/goals/", body)),
  recordActual: (kpiId: string, value: string) =>
    unwrap<unknown>(api.post(`/goals/kpis/${kpiId}/actuals`, { value })),
  approve: (id: string) => unwrap<Goal>(api.post(`/goals/${id}/approve`, {})),
};

// ---- 360 Feedback ----------------------------------------------------------

export const feedbackApi = {
  summariesReview: (params: PageParams = {}) =>
    unwrap<Paginated<FeedbackSummary>>(api.get("/feedback/summaries/review", { params })),
  approveSummary: (id: string) =>
    unwrap<FeedbackSummary>(api.post(`/feedback/summaries/${id}/approve`, {})),
  requestsMine: () =>
    unwrap<FeedbackRequestItem[]>(api.get("/feedback/requests/mine")),
  declineRequest: (id: string) =>
    unwrap<FeedbackRequestItem>(api.post(`/feedback/requests/${id}/decline`, {})),
  mine: (params: PageParams = {}) =>
    unwrap<Paginated<OwnFeedback>>(api.get("/feedback/mine", { params })),
  give: (cycleId: string, body: { body: string; marked_sensitive?: boolean }) =>
    unwrap<OwnFeedback>(api.post(`/feedback/cycles/${cycleId}/give`, body)),
  cycles: (params: PageParams = {}) =>
    unwrap<Paginated<FeedbackCycle>>(api.get("/feedback/cycles", { params })),
  // Subject self-discovery: the cycles ABOUT the caller (own-only, any role),
  // with the released-summary id/status so "My 360" needs no pasted id.
  myCycles: (params: PageParams = {}) =>
    unwrap<Paginated<MyFeedbackCycle>>(api.get("/feedback/my-cycles", { params })),
  createCycle: (body: { subject: string; min_volume?: number }) =>
    unwrap<FeedbackCycle>(api.post("/feedback/cycles", body)),
  openCycle: (id: string) =>
    unwrap<FeedbackCycle>(api.post(`/feedback/cycles/${id}/open`, {})),
  invitations: (cycleId: string) =>
    unwrap<FeedbackRequestItem[]>(api.get(`/feedback/cycles/${cycleId}/requests`)),
  invite: (cycleId: string, body: { giver: string; relationship: string }) =>
    unwrap<FeedbackRequestItem>(api.post(`/feedback/cycles/${cycleId}/requests`, body)),
  closeCycle: (id: string) =>
    unwrap<{ cycle: FeedbackCycle; summary: FeedbackSummarizeResult }>(
      api.post(`/feedback/cycles/${id}/close`, {}),
    ),
  summarize: (id: string) =>
    unwrap<FeedbackSummarizeResult>(api.post(`/feedback/cycles/${id}/summarize`, {})),
  anonymized: (id: string) =>
    unwrap<AnonymizedPayload>(api.get(`/feedback/cycles/${id}/anonymized`)),
  summary: (id: string) =>
    unwrap<FeedbackSummary>(api.get(`/feedback/cycles/${id}/summary`)),
};

// ---- Career ----------------------------------------------------------------

export const careerApi = {
  // Reads
  roadmap: () => unwrap<Paginated<DevelopmentRoadmap>>(api.get("/career/roadmap")),
  roadmaps: (params: PageParams & { employee?: string } = {}) =>
    unwrap<Paginated<DevelopmentRoadmap>>(api.get("/career/roadmaps", { params })),
  detail: (id: string) => unwrap<DevelopmentRoadmap>(api.get(`/career/roadmaps/${id}`)),
  skillGap: (id: string) => unwrap<SkillGap>(api.get(`/career/roadmaps/${id}/skill-gap`)),
  progress: (id: string) =>
    unwrap<RoadmapProgressItem[]>(api.get(`/career/roadmaps/${id}/progress`)),
  // Target selection → deterministic roadmap (employee defaults to the caller).
  selectTarget: (body: { employee?: string; target_jd?: string; target_position?: string }) =>
    unwrap<TargetSelectResult>(api.post("/career/target", body)),
  // Deterministic refresh of the roadmap's gap + tiers.
  regenerate: (id: string) =>
    unwrap<DevelopmentRoadmap>(api.post(`/career/roadmaps/${id}/regenerate`, {})),
  // AI enrich seam — creates a NEW source=AI DRAFT roadmap (503 when no provider).
  enrich: (id: string) =>
    unwrap<RoadmapEnrichResult>(api.post(`/career/roadmaps/${id}/enrich`, {})),
  // Mark a tier's progress (upsert per roadmap+tier).
  setProgress: (id: string, body: { tier_index: number; status: RoadmapProgressStatus }) =>
    unwrap<RoadmapProgressItem>(api.post(`/career/roadmaps/${id}/progress`, body)),
};
