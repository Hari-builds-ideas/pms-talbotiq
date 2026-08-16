import { api } from "./client";
import type {
  AdminUser,
  AdminUserStats,
  AIJob,
  ApprovalRoute,
  ApprovalWorkflow,
  AnonymizedPayload,
  AuditLog,
  BenchCandidate,
  CalibrationGrid,
  ChatActionResult,
  ChatPlanResponse,
  ChatResponse,
  ChatSessionDetail,
  ChatSessionSummary,
  ChatStepApproveResult,
  CheckIn,
  CheckInPriorityStatus,
  CriticalRole,
  CycleScore,
  DevelopmentRoadmap,
  SkillGap,
  RoadmapProgressItem,
  RoadmapProgressStatus,
  TargetSelectResult,
  FeedbackCycle,
  FeedbackRequestItem,
  FeedbackSummary,
  MyFeedbackCycle,
  Goal,
  GoalDraftResponse,
  GoalUpdate,
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
  MeetingSummaryResponse,
  NineBoxPlacement,
  Nudge,
  ReviewQualityResponse,
  StaleGoalsResponse,
  RawOrgTree,
  Paginated,
  PerformanceCycle,
  PersonCard,
  PersonRef,
  Position,
  RecognitionAnalytics,
  RecognitionCard,
  RecognitionMeta,
  RecognitionVisibility,
  Review,
  ReviewAssessment,
  ReviewComment,
  ReviewTransition,
  SuccessionDashboard,
  SuccessionPlan,
  TenantConfig,
  TenantIntegration,
  TokenPair,
  UpgradePrompt,
} from "../types";
import type {
  FeaturePack,
  IntegrationKind,
  Readiness,
  Role,
} from "../enums";

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

export interface AdminUserParams extends PageParams {
  /** Server-side filter: email / display name / role (case-insensitive substring). */
  search?: string;
}

// ---- Auth ------------------------------------------------------------------

/** Pre-login facts the SPA needs before anyone is signed in (C7). Served rather
 *  than baked in at build time, so flipping SIGNUP_MODE takes effect on reload
 *  instead of needing a frontend rebuild. */
export interface PublicConfig {
  signup_open: boolean;
  support_email: string | null;
  google_sso: boolean;
  app_name: string;
}

export const authApi = {
  /** PUBLIC — no token required. */
  publicConfig: () => unwrap<PublicConfig>(api.get("/auth/public-config")),
  login: (body: { email: string; password: string; tenant_slug: string }) =>
    unwrap<import("../types").LoginResponse>(api.post("/auth/login", body)),
  // Self-serve new-organization signup (PROD_B): creates a workspace + first
  // admin and logs them in. Returns tenant-scoped tokens + the workspace slug.
  signup: (body: {
    org_name: string;
    display_name: string;
    email: string;
    password: string;
    workspace_slug?: string;
  }) =>
    unwrap<TokenPair & { tenant_slug: string; workspace_name: string }>(
      api.post("/auth/signup", body),
    ),
  // Field names match the REAL backend contract (apps/identity): the login
  // response's `mfa_token` is posted back with the TOTP code.
  mfaChallenge: (body: { mfa_token: string; code: string }) =>
    unwrap<TokenPair>(api.post("/auth/mfa/challenge", body)),
  mfaEnroll: () =>
    unwrap<{ secret: string; config_url: string }>(api.post("/auth/mfa/enroll", {})),
  mfaEnrollConfirm: (body: { code: string }) =>
    unwrap<{ ok: boolean }>(api.post("/auth/mfa/enroll/confirm", body)),
  me: () => unwrap<Me>(api.get("/auth/me")),
  // Server-side revocation needs the refresh token in the body (the server
  // blacklists it) — callers pass it BEFORE clearing local storage.
  logout: (refresh?: string | null) =>
    unwrap<unknown>(api.post("/auth/logout", refresh ? { refresh } : {})),
  // Self-service password reset — always 200 (no account enumeration).
  passwordResetRequest: (body: { tenant_slug: string; email: string }) =>
    unwrap<{ ok: boolean }>(api.post("/auth/password-reset", body)),
  passwordResetConfirm: (body: {
    tenant_slug: string;
    uid: string;
    token: string;
    new_password: string;
  }) => unwrap<{ ok: boolean }>(api.post("/auth/password-reset/confirm", body)),
  // ── PHASE2 L1.1/L1.3 — profile, security, sessions (all self-scoped) ──
  profile: () => unwrap<import("../types").Profile>(api.get("/auth/profile")),
  profileUpdate: (body: Partial<Pick<import("../types").Profile, "display_name" | "phone" | "timezone" | "language" | "preferences">>) =>
    unwrap<import("../types").Profile>(api.patch("/auth/profile", body)),
  photoUpload: (file: File | Blob) => {
    const form = new FormData();
    form.append("photo", file);
    return unwrap<{ ok: boolean }>(api.put("/auth/profile/photo", form));
  },
  photoDelete: () => unwrap<{ ok: boolean }>(api.delete("/auth/profile/photo")),
  passwordChange: (body: { current_password: string; new_password: string }) =>
    unwrap<{ ok: boolean } & TokenPair>(api.post("/auth/password-change", body)),
  emailChangeRequest: (body: { new_email: string; current_password: string }) =>
    unwrap<{ ok: boolean }>(api.post("/auth/email-change", body)),
  emailChangeConfirm: (token: string) =>
    unwrap<{ ok: boolean; email: string }>(api.post("/auth/email-change/confirm", { token })),
  mfaDisable: (current_password: string) =>
    unwrap<{ ok: boolean }>(api.post("/auth/mfa/disable", { current_password })),
  sessions: () => unwrap<import("../types").DeviceSessionRow[]>(api.get("/auth/sessions")),
  sessionRevoke: (id: string) =>
    unwrap<{ ok: boolean }>(api.post(`/auth/sessions/${id}/revoke`, {})),
  sessionsRevokeOthers: () =>
    unwrap<{ ok: boolean; revoked: number }>(api.post("/auth/sessions/revoke-others", {})),
  loginHistory: () => unwrap<import("../types").LoginEventRow[]>(api.get("/auth/login-history")),
  myActivity: () => unwrap<import("../types").ActivityRow[]>(api.get("/auth/my-activity")),
};

// ---- Billing ---------------------------------------------------------------

export const billingApi = {
  myFeatures: () => unwrap<FeatureFlags>(api.get("/billing/my-features")),
  // ── PHASE2 L1.4 — the internal subscription (Admin) ──
  subscription: () =>
    unwrap<import("../types").SubscriptionInfo>(api.get("/billing/subscription")),
  subscriptionUpdate: (body: { plan?: string; status?: string }) =>
    unwrap<import("../types").SubscriptionInfo>(api.patch("/billing/subscription", body)),
  featureFlags: () => unwrap<FeatureFlags>(api.get("/billing/feature-flags")),
  entitlement: () => unwrap<Entitlement>(api.get("/billing/entitlement")),
  upgradePrompt: () => unwrap<UpgradePrompt>(api.get("/billing/upgrade-prompt")),
  upgrade: (body: { pack: FeaturePack }) =>
    unwrap<Entitlement>(api.post("/billing/upgrade", body)),
  setSeats: (body: { seat_count: number }) =>
    unwrap<Entitlement>(api.patch("/billing/seats", body)),
  // ── PROD_C — payments (Stripe + Razorpay, test mode; Admin) ──
  paymentsConfig: () =>
    unwrap<{
      payments_enabled: boolean;
      stripe_publishable_key: string;
      prices: Record<string, Record<string, Record<string, number>>>;
      cycles: string[];
    }>(api.get("/billing/payments-config")),
  checkout: (body: { plan: string; cycle?: string }) =>
    unwrap<{
      status: "activated" | "pending";
      paid: boolean;
      plan: string;
      cycle?: string;
      amount?: number;
      currency?: string;
      checkout_url?: string;
      session_id?: string;
    }>(api.post("/billing/checkout", body)),
  invoices: () =>
    unwrap<
      {
        id: string;
        number: string;
        total: number;
        currency: string;
        line_items: unknown[];
        issued_at: string;
      }[]
    >(api.get("/billing/invoices")),
};

// ---- Admin -----------------------------------------------------------------

export const adminApi = {
  users: (params: AdminUserParams = {}) =>
    unwrap<Paginated<AdminUser>>(api.get("/admin/users", { params })),
  // ── invitations (PHASE2 L1.2; HRBP+) ──
  invitations: () => unwrap<import("../types").InvitationRow[]>(api.get("/admin/invitations")),
  invite: (body: { email: string; role: Role; manager?: string | null }) =>
    unwrap<import("../types").InvitationRow & { emailed: boolean }>(
      api.post("/admin/invitations", body),
    ),
  inviteRevoke: (id: string) =>
    unwrap<{ ok: boolean }>(api.post(`/admin/invitations/${id}/revoke`, {})),
  inviteResend: (id: string) =>
    unwrap<import("../types").InvitationRow & { emailed: boolean }>(
      api.post(`/admin/invitations/${id}/resend`, {}),
    ),
  userStats: () => unwrap<AdminUserStats>(api.get("/admin/users/stats")),
  // Bulk employee onboarding (PROD_B; HRBP+). CSV with header row:
  // name,email,role,department,designation,manager. Idempotent (upsert by email).
  bulkImport: (file: File | Blob) => {
    const form = new FormData();
    form.append("file", file);
    return unwrap<{
      created: number;
      updated: number;
      skipped: number;
      total: number;
      errors: { row: number | string; email: string; error: string }[];
    }>(api.post("/admin/users/import", form));
  },
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
  saveTenantConfig: (settings: Record<string, unknown>, version?: number) =>
    unwrap<TenantConfig>(api.put("/admin/tenant-config", { settings, version })),
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
  // One employee's score, scope-bound (404 out-of-scope / not-yet-computed) —
  // for single-person consumers that shouldn't pull the whole cohort.
  score: (cycleId: string, employeeId: string) =>
    unwrap<CycleScore>(api.get(`/cycles/${cycleId}/scores/${employeeId}`)),
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
  comments: (id: string) =>
    unwrap<ReviewComment[]>(api.get(`/reviews/${id}/comments`)),
  createComment: (
    id: string,
    body: { body: string; section?: string | null; parent?: string | null },
  ) => unwrap<ReviewComment>(api.post(`/reviews/${id}/comments`, body)),
  editComment: (reviewId: string, commentId: string, body: string) =>
    unwrap<ReviewComment>(api.patch(`/reviews/${reviewId}/comments/${commentId}`, { body })),
  deleteComment: (reviewId: string, commentId: string) =>
    unwrap<void>(api.delete(`/reviews/${reviewId}/comments/${commentId}`)),
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
  // AI draft seam — async: returns an AIJob (202); poll aiJobsApi.get(job.id).
  requestAiDraft: (id: string) =>
    unwrap<AIJob>(api.post(`/reviews/${id}/request-ai-draft`, {})),
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
  // AI generate seam — async: returns an AIJob (202); poll aiJobsApi.get(job.id).
  generate: (id: string, body: { prompt?: string }) =>
    unwrap<AIJob>(api.post(`/jd/${id}/generate`, body)),
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
  // Returns the raw wire shape; callers normalize via normalizeOrgTree (see useOrgTree).
  // Optional lazy params: { root } = subtree under a node, { depth } = N levels.
  tree: (params: { root?: string; depth?: number } = {}) =>
    unwrap<RawOrgTree>(api.get("/org/tree", { params })),
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
  setNineBoxOverride: (placementId: string, box: number, rationale?: string) =>
    unwrap<NineBoxPlacement>(
      api.put(`/succession/nine-box/${placementId}/override`, { box, rationale }),
    ),
  clearNineBoxOverride: (placementId: string) =>
    unwrap<NineBoxPlacement>(api.delete(`/succession/nine-box/${placementId}/override`)),
  plan: (id: string) => unwrap<SuccessionPlan>(api.get(`/succession/plans/${id}`)),
  addActionItem: (id: string, text: string) =>
    unwrap<SuccessionPlan>(api.post(`/succession/plans/${id}/action-item`, { text })),
  publishPlan: (id: string) =>
    unwrap<SuccessionPlan>(api.post(`/succession/plans/${id}/publish`, {})),
  // AI enrich seam — async: returns an AIJob (202); poll aiJobsApi.get(job.id).
  enrichPlan: (id: string) =>
    unwrap<AIJob>(api.post(`/succession/plans/${id}/enrich`, {})),
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

/** What the admin AI-config endpoint is allowed to tell us. Note the absence of
 *  the key itself: the server has no endpoint that returns it, by design. */
export interface AIConfigState {
  enabled: boolean;
  provider: string;
  model_overrides: Record<string, string>;
  /** Will an AI request work right now, from any key source? */
  configured: boolean;
  key_source: "tenant" | "environment" | "unconfigured";
  tenant_key_set: boolean;
  /** Masked hint, e.g. "••••9xyz". Never the key. */
  key_hint: string;
  key_set_at: string | null;
  /** False when FIELD_ENCRYPTION_KEY is unset — storing a key is impossible. */
  encryption_available: boolean;
  available_providers: string[];
  changed?: string[];
}

export interface AIConnectionTest {
  ok: boolean;
  state:
    | "ok"
    | "not_configured"
    | "ai_disabled"
    | "budget_exceeded"
    | "provider_error";
  detail: string;
  provider?: string;
  model?: string;
  key_source?: string;
}

/** This tenant's AI consumption and estimated cost (B6). The tenant is taken
 *  from the caller server-side — there is deliberately no tenant parameter. */
export interface AIUsage {
  days: number;
  since: string;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  /** Models with usage but no price entry — reported rather than folded in as 0,
   *  because a silent zero reads as "this was free". */
  unpriced_models: string[];
  by_agent: { agent_code: string; calls: number; tokens: number; cost_usd: number }[];
  by_model: { model: string; calls: number; tokens: number; cost_usd: number }[];
  budgets: { agent_code: string; window: string; limit: number }[];
  cost_is_estimate: boolean;
  note: string;
}

/** Admin Hub — AI provider configuration (B2). MANAGE_TENANT_CONFIG (Admin). */
export const aiAdminApi = {
  /** MANAGE_TENANT (Admin). `days` is clamped 1..365 server-side. */
  usage: (days = 30) =>
    unwrap<AIUsage>(api.get("/billing/ai-usage", { params: { days } })),
  config: () => unwrap<AIConfigState>(api.get("/ai/admin/config")),
  update: (body: {
    enabled?: boolean;
    provider?: string;
    model_overrides?: Record<string, string>;
    api_key?: string;
    clear_api_key?: boolean;
  }) => unwrap<AIConfigState>(api.patch("/ai/admin/config", body)),
  testConnection: () =>
    unwrap<AIConnectionTest>(api.post("/ai/admin/test-connection", {})),
};

export const aiApi = {
  chat: (query: string, sessionId?: string) =>
    unwrap<ChatResponse>(api.post("/ai/chat", { query, session_id: sessionId })),
  // RW_BUILD_4 — run a previously PROPOSED assistant action on explicit human
  // Approve. The server re-checks permission + scope and audits each effect.
  executeAction: (action: string, params: Record<string, unknown>) =>
    unwrap<ChatActionResult>(api.post("/ai/actions/execute", { action, params })),
  nudges: () => unwrap<Nudge[]>(api.get("/ai/nudges")),
  // RW_BUILD_5 quick win — stateless AI summary of meeting / 1-on-1 notes.
  // DRAFT only; persists nothing. 503 (no provider) / 429 (over budget) surface
  // as mapApiError kinds the caller can render.
  meetingSummary: (notes: string) =>
    unwrap<MeetingSummaryResponse>(api.post("/ai/meeting-summary", { notes })),
  // RW_BUILD_5 quick win — ADVISORY quality/bias flags on a draft review's text
  // (MANAGE_REVIEWS). Never blocks; persists nothing. Same 503/429 error kinds.
  reviewQuality: (text: string) =>
    unwrap<ReviewQualityResponse>(api.post("/ai/review-quality", { text })),
  // RW_BUILD_5 quick win — stale ACTIVE goals in the caller's scope (VIEW_TEAM_SCORES)
  // + ONE advisory AI follow-up suggestion. READ-ONLY; the list always returns (the
  // suggestion is null when the AI is unavailable), so this 200s rather than 503-ing.
  staleGoals: () => unwrap<StaleGoalsResponse>(api.get("/ai/stale-goals")),
  // OVERNIGHT_A — the AGENT surface: plan a (multi-step) request into an INERT
  // checklist; nothing runs until a per-step approve. Optionally resumes a session.
  plan: (query: string, sessionId?: string) =>
    unwrap<ChatPlanResponse>(api.post("/ai/chat/plan", { query, session_id: sessionId })),
  // Approve + run EXACTLY ONE step (server re-checks capability + scope, audits).
  approveStep: (planId: string, stepId: string) =>
    unwrap<ChatStepApproveResult>(api.post(`/ai/chat/plan/${planId}/step/${stepId}/approve`, {})),
  // Recent, non-expired chat sessions (the resume picker) + one session's turns.
  listSessions: () => unwrap<ChatSessionSummary[]>(api.get("/ai/chat/sessions")),
  getSession: (id: string) => unwrap<ChatSessionDetail>(api.get(`/ai/chat/sessions/${id}`)),
};

// ---- Async AI jobs (poll surface) ------------------------------------------

export const aiJobsApi = {
  get: (id: string) => unwrap<AIJob>(api.get(`/ai/jobs/${id}`)),
  listForTarget: (target: string) =>
    unwrap<AIJob[]>(api.get("/ai/jobs", { params: { target } })),
};

// ---- Goals & KPIs ----------------------------------------------------------

export const goalsApi = {
  list: (params: PageParams & { employee?: string; cycle?: string } = {}) =>
    unwrap<Paginated<Goal>>(api.get("/goals/", { params })),
  // RW_BUILD_5 — AI goal-writer: a one-line intent → an editable SMART goal DRAFT
  // (persists nothing; the human edits + creates it the normal way).
  aiDraft: (prompt: string) =>
    unwrap<GoalDraftResponse>(api.post("/goals/ai-draft", { prompt })),
  detail: (id: string) => unwrap<Goal>(api.get(`/goals/${id}`)),
  // AGENT_UX_V3 Part 2.3 — the goal's progress-notes timeline.
  goalUpdates: (id: string) => unwrap<GoalUpdate[]>(api.get(`/goals/${id}/updates`)),
  addGoalUpdate: (id: string, text: string) =>
    unwrap<GoalUpdate>(api.post(`/goals/${id}/updates`, { text })),
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
  // Close is synchronous; the summarize seam it fires is async — the enqueued
  // AIJob rides back under `job` (poll aiJobsApi.get(job.id)).
  closeCycle: (id: string) =>
    unwrap<{ cycle: FeedbackCycle; job: AIJob }>(
      api.post(`/feedback/cycles/${id}/close`, {}),
    ),
  // AI summarize seam — async: returns an AIJob (202); poll aiJobsApi.get(job.id).
  summarize: (id: string) =>
    unwrap<AIJob>(api.post(`/feedback/cycles/${id}/summarize`, {})),
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
  // AI enrich seam — async: returns an AIJob (202); poll aiJobsApi.get(job.id).
  enrich: (id: string) =>
    unwrap<AIJob>(api.post(`/career/roadmaps/${id}/enrich`, {})),
  // Adopt an AI-enriched DRAFT as the ACTIVE roadmap (HITL acceptance).
  adopt: (id: string) =>
    unwrap<DevelopmentRoadmap>(api.post(`/career/roadmaps/${id}/adopt`, {})),
  // Mark a tier's progress (upsert per roadmap+tier).
  setProgress: (id: string, body: { tier_index: number; status: RoadmapProgressStatus }) =>
    unwrap<RoadmapProgressItem>(api.post(`/career/roadmaps/${id}/progress`, body)),
};

// ── RW_BUILD_2 — Recognition (kudos card + feed). Visibility is enforced
// server-side; the feed returns only what the caller is permitted to see. ──
export const recognitionApi = {
  feed: () => unwrap<RecognitionCard[]>(api.get("/recognition/")),
  meta: () => unwrap<RecognitionMeta>(api.get("/recognition/meta")),
  analytics: () => unwrap<RecognitionAnalytics>(api.get("/recognition/analytics")),
  give: (body: {
    recipient: string;
    value: string;
    message: string;
    visibility: RecognitionVisibility;
    badge?: string;
  }) => unwrap<RecognitionCard>(api.post("/recognition/", body)),
  react: (id: string, emoji: string) =>
    unwrap<{ recognition: string; emoji: string; reacted: boolean }>(
      api.post(`/recognition/${id}/react`, { emoji }),
    ),
  remove: (id: string) => api.delete(`/recognition/${id}`),
};

// ── RW_BUILD_3 — Weekly Check-ins. Scope is enforced server-side (own / a
// manager's reporting subtree); cross-manager + cross-tenant → 404. ──
export const checkinsApi = {
  mine: () => unwrap<CheckIn[]>(api.get("/checkins/")),
  team: () => unwrap<CheckIn[]>(api.get("/checkins/team")),
  detail: (id: string) => unwrap<CheckIn>(api.get(`/checkins/${id}`)),
  upsert: (body: {
    week_of: string;
    mood: number;
    wins?: string;
    blockers?: string;
    learning?: string;
    priorities?: { text: string; status?: CheckInPriorityStatus }[];
  }) => unwrap<CheckIn>(api.post("/checkins/", body)),
  respond: (
    id: string,
    body: { comment?: string; reaction?: string; follow_up?: boolean; add_to_one_on_one?: boolean },
  ) => unwrap<CheckIn>(api.post(`/checkins/${id}/respond`, body)),
};
