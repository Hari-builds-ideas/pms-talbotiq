/**
 * Mock data store. Shapes match the contract 1:1 (field names, enum values,
 * pagination envelope) so swapping VITE_USE_MOCKS=false maps cleanly onto the
 * live API. State is mutable in-memory so actions (create/approve/upgrade…)
 * feel real for the session; reload reseeds.
 */
import type {
  AdminUser,
  ApprovalRoute,
  ApprovalWorkflow,
  AuditLog,
  BenchCandidate,
  CalibrationGrid,
  CriticalRole,
  DepartmentAnalytics,
  Entitlement,
  FeatureFlags,
  InboxItem,
  JdRequest,
  JdVersion,
  JobDescription,
  Me,
  NineBoxPlacement,
  Nudge,
  OrgNode,
  RawOrgTree,
  Position,
  Review,
  ReviewAssessment,
  ReviewTransition,
  SuccessionPlan,
  TenantConfig,
  TenantIntegration,
} from "@/lib/types";
import type { FeatureKey } from "@/lib/enums";

export const TENANT = { id: "t-acme", name: "Acme Corp", slug: "acme" };

// ---- Users -----------------------------------------------------------------

export const USERS: AdminUser[] = [
  {
    id: "u-admin-001",
    email: "admin@acme.test",
    display_name: "Avery Stone",
    display: "Avery Stone",
    role: "ADMIN",
    manager: null,
    is_active: true,
    mfa_enabled: false,
  },
  {
    id: "u-hrbp",
    email: "hrbp@acme.test",
    display_name: "Priya Nair",
    display: "Priya Nair",
    role: "HRBP",
    manager: "u-admin-001",
    is_active: true,
    mfa_enabled: false,
  },
  {
    id: "u-1",
    email: "ada@acme.test",
    display_name: "Ada Lovelace",
    display: "Ada Lovelace",
    role: "MANAGER",
    manager: "u-hrbp",
    is_active: true,
    mfa_enabled: true,
  },
  {
    id: "u-2",
    email: "reza@acme.test",
    display_name: null,
    display: "reza@acme.test",
    role: "EMPLOYEE",
    manager: "u-1",
    is_active: true,
    mfa_enabled: false,
  },
  {
    id: "u-3",
    email: "old@acme.test",
    display_name: "Former Person",
    display: "Former Person",
    role: "EMPLOYEE",
    manager: "u-1",
    is_active: false,
    mfa_enabled: false,
  },
  {
    id: "u-4",
    email: "sam@acme.test",
    display_name: "Sam Okafor",
    display: "Sam Okafor",
    role: "EMPLOYEE",
    manager: "u-1",
    is_active: true,
    mfa_enabled: false,
  },
  {
    id: "u-5",
    email: "lin@acme.test",
    display_name: "Lin Zhao",
    display: "Lin Zhao",
    role: "MANAGER",
    manager: "u-hrbp",
    is_active: true,
    mfa_enabled: false,
  },
  {
    id: "u-6",
    email: "omar@acme.test",
    display_name: "Omar Haddad",
    display: "Omar Haddad",
    role: "EMPLOYEE",
    manager: "u-5",
    is_active: true,
    mfa_enabled: false,
  },
  {
    id: "u-7",
    email: "mia@acme.test",
    display_name: "Mia Fontaine",
    display: "Mia Fontaine",
    role: "EMPLOYEE",
    manager: "u-5",
    is_active: true,
    mfa_enabled: false,
  },
  {
    id: "u-8",
    email: "noah@acme.test",
    display_name: "Noah Bergström",
    display: "Noah Bergström",
    role: "EMPLOYEE",
    manager: "u-5",
    is_active: true,
    mfa_enabled: false,
  },
];

export function userById(id: string | null | undefined): AdminUser | undefined {
  if (!id) return undefined;
  return USERS.find((u) => u.id === id);
}

export function displayOf(id: string | null | undefined): string {
  return userById(id)?.display ?? "—";
}

/** The four primary login identities surfaced in the dev role switcher. */
export const LOGIN_IDENTITIES = [
  { id: "u-admin-001", label: "Admin", email: "admin@acme.test" },
  { id: "u-hrbp", label: "HRBP", email: "hrbp@acme.test" },
  { id: "u-1", label: "Manager", email: "ada@acme.test" },
  { id: "u-2", label: "Employee", email: "reza@acme.test" },
] as const;

export function meFor(id: string): Me | undefined {
  const u = userById(id);
  if (!u) return undefined;
  return {
    id: u.id,
    email: u.email,
    display_name: u.display_name,
    display: u.display,
    role: u.role,
    tenant_id: TENANT.id,
    manager_id: u.manager,
    mfa_enabled: u.mfa_enabled,
  };
}

// ---- Billing / entitlements ------------------------------------------------

export const store = {
  /** Current entitlement (mutated by upgrade / seats). */
  entitlement: {
    seat_count: 25,
    feature_packs: ["STARTER"],
    unlocked_agents: ["agent2"],
    tier_label: "Starter",
  } as Entitlement,

  featureFlags: {
    agent1: false,
    agent2: true,
    agent3: false,
    agent4: false,
    agent5: false,
    chat: true,
    jd_generator: false,
    career_roadmap: false,
  } as FeatureFlags,

  tenantConfig: {
    id: "cfg-1",
    settings: { locale: "en-GB", weekStart: "MON", fiscalYearStart: "04-01" },
    version: 0,
  } as TenantConfig,
};

const FULL_AI_FLAGS: FeatureKey[] = [
  "agent1",
  "agent3",
  "agent4",
  "agent5",
  "jd_generator",
  "career_roadmap",
];

export function upgradeToFullAi(): Entitlement {
  store.entitlement = {
    ...store.entitlement,
    feature_packs: ["STARTER", "FULL_AI"],
    unlocked_agents: ["agent1", "agent2", "agent3", "agent4", "agent5"],
    tier_label: "Full AI",
  };
  for (const f of FULL_AI_FLAGS) store.featureFlags[f] = true;
  return store.entitlement;
}

export function lockedFeatures(): FeatureKey[] {
  return (Object.keys(store.featureFlags) as FeatureKey[]).filter(
    (k) => !store.featureFlags[k],
  );
}

// ---- Cycles ----------------------------------------------------------------

export const CYCLES = [
  { id: "cy-1", name: "H1 2026", start_date: "2026-01-01", end_date: "2026-06-30", status: "ACTIVE" },
  { id: "cy-0", name: "H2 2025", start_date: "2025-07-01", end_date: "2025-12-31", status: "CLOSED" },
];

// ---- Approvals -------------------------------------------------------------

export const workflows: ApprovalWorkflow[] = [
  {
    id: "wf-1",
    name: "Review sign-off",
    artifact_type: "review",
    mode: "SEQUENTIAL",
    active: true,
    steps: [
      { order: 1, approver_kind: "ROLE", approver_role: "MANAGER", required: true, timeout_hours: 48 },
      { order: 2, approver_kind: "ROLE", approver_role: "HRBP", required: true, timeout_hours: 48 },
    ],
  },
  {
    id: "wf-2",
    name: "JD publication (parallel)",
    artifact_type: "jd",
    mode: "PARALLEL",
    active: false,
    steps: [
      { order: 1, approver_kind: "ROLE", approver_role: "HRBP", required: true, timeout_hours: 72 },
      { order: 2, approver_kind: "NAMED", approver_user: "u-admin-001", required: false, timeout_hours: 72 },
    ],
  },
];

export const routes: ApprovalRoute[] = [
  {
    id: "rt-7",
    status: "IN_PROGRESS",
    mode: "SEQUENTIAL",
    artifact_type: "review",
    artifact_id: "rv-3",
    initiated_by: "u-1",
    step_instances: [
      { id: "si-8", order: 1, approver: "u-1", approver_role: "MANAGER", status: "APPROVED", decided_by: "u-1", decided_at: "2026-06-12T10:00:00Z", comment: "Strong half — endorsed.", escalated: false, due_at: null },
      { id: "si-9", order: 2, approver: null, approver_role: "HRBP", status: "PENDING", decided_by: null, decided_at: null, comment: "", escalated: false, due_at: "2026-06-20T17:00:00Z" },
    ],
  },
  {
    id: "rt-8",
    status: "IN_PROGRESS",
    mode: "PARALLEL",
    artifact_type: "jd",
    artifact_id: "jd-2",
    initiated_by: "u-hrbp",
    step_instances: [
      { id: "si-10", order: 1, approver: null, approver_role: "HRBP", status: "PENDING", decided_by: null, decided_at: null, comment: "", escalated: false, due_at: "2026-06-18T17:00:00Z" },
      { id: "si-11", order: 2, approver: "u-admin-001", approver_role: "ADMIN", status: "PENDING", decided_by: null, decided_at: null, comment: "", escalated: true, due_at: "2026-06-14T17:00:00Z" },
    ],
  },
];

/** Inbox per role (SEQUENTIAL surfaces only the active step). */
export function inboxFor(role: string): InboxItem[] {
  const items: InboxItem[] = [];
  for (const route of routes) {
    if (route.status !== "IN_PROGRESS") continue;
    const active =
      route.mode === "SEQUENTIAL"
        ? route.step_instances.find((s) => s.status === "PENDING")
        : undefined;
    const candidates =
      route.mode === "SEQUENTIAL"
        ? active
          ? [active]
          : []
        : route.step_instances.filter((s) => s.status === "PENDING");
    for (const step of candidates) {
      if (step.approver_role === role || step.approver === meIdForRole(role)) {
        items.push({
          id: step.id!,
          route: route.id,
          order: step.order,
          approver: step.approver,
          approver_role: step.approver_role,
          status: step.status,
          due_at: step.due_at,
          artifact_type: route.artifact_type,
          artifact_id: route.artifact_id,
          escalated: step.escalated,
        });
      }
    }
  }
  return items;
}

function meIdForRole(role: string): string | undefined {
  return USERS.find((u) => u.role === role)?.id;
}

// ---- Reviews ---------------------------------------------------------------

export const reviews: Review[] = [
  {
    id: "rv-1", employee: "u-2", reviewer: "u-1", cycle: "cy-1", state: "PENDING_HUMAN_REVIEW",
    draft_body: "Reza delivered the data-pipeline migration ahead of schedule and mentored a new hire. Growth area: stakeholder communication on cross-team dependencies.",
    final_body: "", human_reviewer: null, approved_at: null, finalized_at: null, rejected_reason: null,
    source: "AI", confidence_score: "0.8600", citations: [{ kpi: "Pipeline uptime" }], approval_route: null,
  },
  {
    id: "rv-2", employee: "u-4", reviewer: "u-1", cycle: "cy-1", state: "DRAFT",
    draft_body: "", final_body: "", human_reviewer: null, approved_at: null, finalized_at: null,
    rejected_reason: null, source: "MANUAL", confidence_score: null, citations: null, approval_route: null,
  },
  {
    id: "rv-3", employee: "u-6", reviewer: "u-5", cycle: "cy-1", state: "APPROVED",
    draft_body: "Omar's quarter was solid; consistent delivery on the billing epics.",
    final_body: "Omar's quarter was solid; consistent delivery on the billing epics. Endorsed for a stretch project next cycle.",
    human_reviewer: "u-5", approved_at: "2026-06-12T09:30:00Z", finalized_at: null, rejected_reason: null,
    source: "MANUAL", confidence_score: null, citations: null, approval_route: "rt-7",
  },
  {
    id: "rv-4", employee: "u-7", reviewer: "u-5", cycle: "cy-1", state: "REJECTED",
    draft_body: "Auto-draft was too generic.", final_body: "", human_reviewer: null, approved_at: null,
    finalized_at: null, rejected_reason: "Needs concrete examples and KPI references before approval.",
    source: "AI", confidence_score: "0.5400", citations: [], approval_route: null,
  },
  {
    id: "rv-5", employee: "u-8", reviewer: "u-5", cycle: "cy-0", state: "FINALIZED",
    draft_body: "", final_body: "Noah exceeded targets across all KPIs and is ready for more ownership.",
    human_reviewer: "u-5", approved_at: "2025-12-10T09:00:00Z", finalized_at: "2025-12-12T16:00:00Z",
    rejected_reason: null, source: "MANUAL", confidence_score: null, citations: null, approval_route: null,
  },
];

export const reviewTimelines: Record<string, ReviewTransition[]> = {
  "rv-1": [
    { from_state: "DRAFT", to_state: "AI_DRAFTING", note: "Requested AI draft", actor: "u-1", at: "2026-06-10T08:00:00Z" },
    { from_state: "AI_DRAFTING", to_state: "PENDING_HUMAN_REVIEW", note: "AI draft ready", actor: null, at: "2026-06-10T08:01:00Z" },
  ],
  "rv-3": [
    { from_state: "DRAFT", to_state: "EDITING", note: "Started editing", actor: "u-5", at: "2026-06-11T10:00:00Z" },
    { from_state: "EDITING", to_state: "PENDING_HUMAN_REVIEW", note: "Submitted for review", actor: "u-5", at: "2026-06-11T11:00:00Z" },
    { from_state: "PENDING_HUMAN_REVIEW", to_state: "APPROVED", note: "Approved", actor: "u-5", at: "2026-06-12T09:30:00Z" },
  ],
};

export const reviewAssessments: Record<string, ReviewAssessment[]> = {
  "rv-1": [
    { id: "ra-1", assessment_type: "SELF", body: "Proud of the migration; want to grow in comms.", assessor: "u-2", submitted_at: "2026-06-08T12:00:00Z" },
    { id: "ra-2", assessment_type: "MANAGER", body: "Reliable and technically strong.", assessor: "u-1", submitted_at: "2026-06-09T12:00:00Z" },
  ],
};

// ---- JD --------------------------------------------------------------------

export const jds: JobDescription[] = [
  { id: "jd-1", title: "Staff Engineer", level: "L5", department: "Engineering", status: "PUBLISHED", source: "MANUAL", current_version: "jdv-1b", created_by: "u-hrbp", approval_route: null },
  { id: "jd-2", title: "Analytics Engineer", level: "L4", department: "Data", status: "PENDING_HUMAN_REVIEW", source: "AI", current_version: null, created_by: "u-hrbp", approval_route: null },
  { id: "jd-3", title: "Site Reliability Engineer", level: "L4", department: "Engineering", status: "DRAFT", source: "MANUAL", current_version: null, created_by: "u-hrbp", approval_route: null },
  { id: "jd-4", title: "Product Designer", level: "L3", department: "Design", status: "ARCHIVED", source: "MANUAL", current_version: "jdv-4", created_by: "u-admin-001", approval_route: null },
];

export const jdVersions: Record<string, JdVersion[]> = {
  "jd-1": [
    { id: "jdv-1b", version_number: 2, is_published: true, confidence_score: null, citations: null, body: { summary: "Owns platform reliability and architecture at scale.", responsibilities: ["Lead platform architecture", "Mentor senior engineers", "Drive reliability roadmap"], must_haves: ["8+ yrs backend", "Distributed systems"], nice_to_haves: ["Go", "Kubernetes"] } },
    { id: "jdv-1a", version_number: 1, is_published: false, confidence_score: "0.8200", citations: [{ type: "inputs_snapshot" }], body: { summary: "Senior engineer for the platform team.", responsibilities: ["Ship features", "Review code"], must_haves: ["5+ yrs"], nice_to_haves: [] } },
  ],
  "jd-2": [
    { id: "jdv-2a", version_number: 1, is_published: false, confidence_score: "0.7400", citations: [{ type: "inputs_snapshot" }], body: { summary: "Builds and maintains analytics data models.", responsibilities: ["Model warehouse data", "Own dbt pipelines", "Partner with analysts"], must_haves: ["SQL", "dbt"], nice_to_haves: ["Python"] } },
  ],
  "jd-4": [
    { id: "jdv-4", version_number: 1, is_published: true, confidence_score: null, citations: null, body: { summary: "Designs end-to-end product experiences.", responsibilities: ["Own design for a product area"], must_haves: ["Portfolio"], nice_to_haves: [] } },
  ],
};

export const jdRequests: JdRequest[] = [
  { id: "jr-1", requested_by: "u-1", title: "SRE", level: "L4", notes: "Urgent backfill for the platform team.", status: "OPEN" },
  { id: "jr-2", requested_by: "u-5", title: "Data Analyst", level: "L3", notes: "Growing the analytics function.", status: "FULFILLED" },
];

// ---- Org -------------------------------------------------------------------

// Returns the RAW wire shape (array nodes + {from,to} edges) the real API emits,
// so the client's normalizeOrgTree path is exercised identically in dev/mock mode.
export function orgTree(): RawOrgTree {
  const byId: Record<string, OrgNode> = {};
  for (const u of USERS) {
    if (!u.is_active) continue;
    byId[u.id] = {
      id: u.id, email: u.email, display: u.display, role: u.role,
      headcount: 0, vacancies: 0, direct_report_ids: [],
    };
  }
  const edges: Array<{ from: string; to: string }> = [];
  for (const u of USERS) {
    if (!u.is_active || !u.manager || !byId[u.manager]) continue;
    edges.push({ from: u.manager, to: u.id });
    byId[u.manager].direct_report_ids.push(u.id);
  }
  for (const n of Object.values(byId)) n.direct_report_ids.sort();
  // headcount = subtree size (inclusive); vacancies = OPEN positions in subtree
  function subtree(id: string): string[] {
    return [id, ...(byId[id]?.direct_report_ids ?? []).flatMap(subtree)];
  }
  for (const n of Object.values(byId)) {
    const sub = subtree(n.id);
    n.headcount = sub.length;
    n.vacancies = positions.filter(
      (p) => p.status === "OPEN" && p.reports_to && sub.includes(p.reports_to),
    ).length;
  }
  // roots = active users with no active manager
  const roots = Object.values(byId)
    .filter((n) => {
      const u = USERS.find((x) => x.id === n.id);
      return !u?.manager || !byId[u.manager];
    })
    .map((n) => n.id)
    .sort();
  return { roots, nodes: Object.values(byId), edges };
}

export const positions: Position[] = [
  { id: "p-1", title: "Engineering Manager", reports_to: "u-hrbp", department: "Engineering", status: "FILLED", filled_by: "u-1", published_jd: "jd-1", opened_at: "2025-09-01T09:00:00Z", filled_at: "2025-10-01T09:00:00Z" },
  { id: "p-2", title: "Site Reliability Engineer", reports_to: "u-1", department: "Engineering", status: "OPEN", filled_by: null, published_jd: "jd-1", opened_at: "2026-06-01T09:00:00Z", filled_at: null },
  { id: "p-3", title: "Data Analyst", reports_to: "u-5", department: "Data", status: "OPEN", filled_by: null, published_jd: null, opened_at: "2026-05-15T09:00:00Z", filled_at: null },
  { id: "p-4", title: "Senior Designer", reports_to: "u-admin-001", department: "Design", status: "CLOSED", filled_by: null, published_jd: null, opened_at: "2026-02-01T09:00:00Z", filled_at: null },
];

// ---- Succession ------------------------------------------------------------

export const criticalRoles: CriticalRole[] = [
  { id: "cr-1", name: "Head of Platform", position: "p-1", incumbent: "u-1", criticality: "CRITICAL", knowledge_risk: "HIGH", risk_notes: "Sole owner of the deploy pipeline.", status: "ACTIVE", coverage_status: "GREEN", published_plan: "sp-1" },
  { id: "cr-2", name: "Lead DBA", position: null, incumbent: "u-5", criticality: "HIGH", knowledge_risk: "MEDIUM", risk_notes: "", status: "ACTIVE", coverage_status: "RED", published_plan: null },
  { id: "cr-3", name: "Principal Designer", position: "p-4", incumbent: null, criticality: "HIGH", knowledge_risk: "LOW", risk_notes: "", status: "ACTIVE", coverage_status: "AMBER", published_plan: null },
];

export const benchByRole: Record<string, BenchCandidate[]> = {
  "cr-1": [
    { id: "bc-1", candidate: "u-4", readiness: "READY_SOON", readiness_overridden: false, notes: "Strong technical depth." },
    { id: "bc-2", candidate: "u-6", readiness: "DEVELOPING", readiness_overridden: true, notes: "" },
  ],
  "cr-2": [
    { id: "bc-3", candidate: "u-8", readiness: "NOT_READY", readiness_overridden: false, notes: "Needs DBA exposure." },
  ],
  "cr-3": [],
};

export const nineBox: NineBoxPlacement[] = [
  { id: "nb-1", employee: "u-1", cycle: "cy-1", performance_band: "HIGH", potential_band: "HIGH", box: 9 },
  { id: "nb-2", employee: "u-2", cycle: "cy-1", performance_band: "MEDIUM", potential_band: "MEDIUM", box: 5 },
  { id: "nb-3", employee: "u-4", cycle: "cy-1", performance_band: "HIGH", potential_band: "MEDIUM", box: 6 },
  { id: "nb-4", employee: "u-6", cycle: "cy-1", performance_band: "MEDIUM", potential_band: "HIGH", box: 8 },
  { id: "nb-5", employee: "u-7", cycle: "cy-1", performance_band: "LOW", potential_band: "MEDIUM", box: 2 },
  { id: "nb-6", employee: "u-8", cycle: "cy-1", performance_band: "HIGH", potential_band: "HIGH", box: 9 },
];

export const plans: Record<string, SuccessionPlan> = {
  "sp-1": {
    id: "sp-1", status: "PENDING_HUMAN_REVIEW", coverage_status: "GREEN", source: "DETERMINISTIC", confidence_score: null,
    ranked_bench: [{ candidate_id: "u-4", readiness: "READY_SOON" }, { candidate_id: "u-6", readiness: "DEVELOPING" }],
    red_flags: [],
    action_items: [{ text: "Pair u-4 with the incumbent for one quarter.", added_by: "u-hrbp" }],
  },
};

// ---- Analytics -------------------------------------------------------------

export function individualTrend(employee: string) {
  return {
    employee,
    trend: [
      { cycle: "cy-1", t_score: "55.0000", risk_status: "ON_TRACK", raw_score: "0.7200", pace_behind: false },
      { cycle: "cy-0", t_score: "42.0000", risk_status: "AT_RISK", raw_score: "0.5500", pace_behind: true },
    ],
  };
}

export function departmentAnalytics(head: string, cycle: string): DepartmentAnalytics {
  // Ada's team is small (suppressed); the HRBP/Lin line is large enough to show.
  const small = head === "u-1";
  if (small) {
    return {
      head, cycle, cohort_size: 3, min_cohort: 5, suppressed: true,
      aggregate: { headcount: 3, scored: 3, mean_t_score: 49.5, median_t_score: 50, risk_distribution: { ON_TRACK: 1, AT_RISK: 2, CRITICAL: 0 } },
      individuals: [],
      note: "Cohort too small (<5); individual values suppressed.",
    };
  }
  return {
    head, cycle, cohort_size: 6, min_cohort: 5, suppressed: false,
    aggregate: { headcount: 6, scored: 6, mean_t_score: 52.3, median_t_score: 51, risk_distribution: { ON_TRACK: 4, AT_RISK: 1, CRITICAL: 1 } },
    individuals: [
      { employee: "u-6", t_score: "58.0000", risk_status: "ON_TRACK" },
      { employee: "u-7", t_score: "38.0000", risk_status: "CRITICAL" },
      { employee: "u-8", t_score: "61.0000", risk_status: "ON_TRACK" },
      { employee: "u-2", t_score: "47.0000", risk_status: "AT_RISK" },
      { employee: "u-4", t_score: "55.0000", risk_status: "ON_TRACK" },
      { employee: "u-1", t_score: "54.0000", risk_status: "ON_TRACK" },
    ],
  };
}

export function calibration(cycle: string): CalibrationGrid {
  const grid: Record<string, number> = { "1": 0, "2": 1, "3": 0, "4": 0, "5": 1, "6": 1, "7": 0, "8": 1, "9": 2 };
  return {
    cycle, total: 6, grid,
    placements: nineBox.map((n) => ({ employee: n.employee, box: n.box, performance_band: n.performance_band, potential_band: n.potential_band })),
  };
}

// ---- Audit -----------------------------------------------------------------

export const auditLogs: AuditLog[] = Array.from({ length: 64 }).map((_, i) => {
  const actions = ["review.approved", "review.finalized", "succession_plan.published", "jd.published", "user.role_changed", "billing.upgraded", "approval.step.approved", "integration.updated"];
  const actors = ["u-admin-001", "u-hrbp", "u-1", "u-5"];
  const targets = ["review", "succession_plan", "job_description", "user", "entitlement", "approval_route"];
  const action = actions[i % actions.length];
  return {
    id: `al-${i + 1}`,
    actor: actors[i % actors.length],
    action,
    target_type: targets[i % targets.length],
    target_id: `${targets[i % targets.length]}-${100 + i}`,
    justification: i % 5 === 0 ? "Quarterly governance review." : "",
    metadata: action === "succession_plan.published" ? { coverage_status: "GREEN" } : {},
    created_at: new Date(Date.UTC(2026, 5, 13, 14, 0, 0) - i * 3_600_000).toISOString(),
  };
});

// ---- Integrations ----------------------------------------------------------

export const integrations: TenantIntegration[] = [
  { id: "int-1", kind: "SLACK", enabled: true, config: { channel: "#perf-ops" }, secret_ref: "SLACK_WEBHOOK_ACME" },
  { id: "int-2", kind: "JIRA", enabled: false, config: { base_url: "https://acme.atlassian.net", email: "bot@acme.test", project: "PERF", value_field: "customfield_actual" }, secret_ref: "JIRA_TOKEN_ACME" },
];

// ---- AI --------------------------------------------------------------------

export function nudgesFor(role: string): Nudge[] {
  if (role === "EMPLOYEE") return []; // 403 handled in the handler
  return [
    { employee: "u-7", level: "CRITICAL", message: "Performance is critical — immediate attention needed." },
    { employee: "u-2", level: "STANDARD", message: "At risk — a check-in is recommended this cycle." },
    { employee: "u-6", level: "SUPPRESSED", message: "Flagged for review (cohort too small to score)." },
  ];
}
