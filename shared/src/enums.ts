/**
 * Enum value sets — verbatim from the frontend contract (03_data_dictionary.md).
 * NEVER invent a value here. These drive type-safety, labels, and badge colors.
 */

export const ROLES = ["EMPLOYEE", "MANAGER", "HRBP", "ADMIN"] as const;
export type Role = (typeof ROLES)[number];

export const ROLE_LABEL: Record<Role, string> = {
  EMPLOYEE: "Employee",
  MANAGER: "Manager",
  HRBP: "HRBP",
  ADMIN: "Admin",
};

/** Role rank for "Manager+", "HRBP+" style capability checks (display only). */
export const ROLE_RANK: Record<Role, number> = {
  EMPLOYEE: 0,
  MANAGER: 1,
  HRBP: 2,
  ADMIN: 3,
};

export const TENANT_STATUS = ["ACTIVE", "SUSPENDED", "CANCELLED"] as const;

export const CYCLE_STATUS = ["DRAFT", "ACTIVE", "CLOSED"] as const;

export const GOAL_STATUS = [
  "DRAFT",
  "ACTIVE",
  "ACHIEVED",
  "MISSED",
  "ARCHIVED",
] as const;

export const KPI_DIRECTION = ["INCREASING", "DECREASING"] as const;
export const KPI_SOURCE = ["MANUAL", "JIRA"] as const;
export const MEASUREMENT_SOURCE = ["MANUAL", "JIRA", "SYSTEM"] as const;

export const RISK_STATUS = ["ON_TRACK", "AT_RISK", "CRITICAL"] as const;
export type RiskStatus = (typeof RISK_STATUS)[number];

export const REVIEW_STATE = [
  "DRAFT",
  "AI_DRAFTING",
  "PENDING_HUMAN_REVIEW",
  "EDITING",
  "APPROVED",
  "REJECTED",
  "FINALIZED",
] as const;
export type ReviewState = (typeof REVIEW_STATE)[number];

export const ASSESSMENT_TYPE = ["SELF", "MANAGER", "PEER", "UPWARD"] as const;

export const REVIEW_SOURCE = ["MANUAL", "AI"] as const;

export const FEEDBACK_CYCLE_STATUS = ["DRAFT", "COLLECTING", "CLOSED"] as const;
export const FEEDBACK_RELATIONSHIP = [
  "SELF",
  "MANAGER",
  "PEER",
  "UPWARD",
] as const;
export const FEEDBACK_REQUEST_STATUS = [
  "PENDING",
  "SUBMITTED",
  "DECLINED",
] as const;
export const FEEDBACK_KIND = ["THREE_SIXTY", "CONTINUOUS"] as const;
export const FEEDBACK_SUMMARY_STATUS = [
  "PENDING_HUMAN_REVIEW",
  "HRBP_HOLD",
  "APPROVED",
  "RELEASED",
] as const;

export const APPROVAL_MODE = ["SEQUENTIAL", "PARALLEL"] as const;
export type ApprovalMode = (typeof APPROVAL_MODE)[number];
export const APPROVER_KIND = ["ROLE", "NAMED"] as const;
export const ROUTE_STATUS = [
  "IN_PROGRESS",
  "APPROVED",
  "REJECTED",
  "ESCALATED",
] as const;
export type RouteStatus = (typeof ROUTE_STATUS)[number];
export const STEP_STATUS = [
  "PENDING",
  "APPROVED",
  "REJECTED",
  "ESCALATED",
  "SKIPPED",
] as const;
export type StepStatus = (typeof STEP_STATUS)[number];

export const JD_STATUS = [
  "DRAFT",
  "PENDING_HUMAN_REVIEW",
  "IN_REVIEW",
  "PUBLISHED",
  "ARCHIVED",
] as const;
export type JdStatus = (typeof JD_STATUS)[number];
export const JD_SOURCE = ["MANUAL", "AI"] as const;
export const JD_REQUEST_STATUS = ["OPEN", "FULFILLED", "DECLINED"] as const;

export const POSITION_STATUS = ["OPEN", "FILLED", "CLOSED"] as const;
export type PositionStatus = (typeof POSITION_STATUS)[number];

export const CRITICALITY = ["HIGH", "CRITICAL"] as const;
export const KNOWLEDGE_RISK = ["LOW", "MEDIUM", "HIGH"] as const;
export const READINESS = [
  "READY_NOW",
  "READY_SOON",
  "DEVELOPING",
  "NOT_READY",
] as const;
export type Readiness = (typeof READINESS)[number];
export const PERFORMANCE_BAND = ["LOW", "MEDIUM", "HIGH"] as const;
export type Band = (typeof PERFORMANCE_BAND)[number];
export const PLAN_STATUS = [
  "DRAFT",
  "PENDING_HUMAN_REVIEW",
  "PUBLISHED",
] as const;
export type PlanStatus = (typeof PLAN_STATUS)[number];
export const COVERAGE_STATUS = ["RED", "AMBER", "GREEN"] as const;
export type CoverageStatus = (typeof COVERAGE_STATUS)[number];
export const PLAN_SOURCE = ["DETERMINISTIC", "AI"] as const;

export const ROADMAP_STATUS = ["DRAFT", "ACTIVE", "ARCHIVED"] as const;
export const ROADMAP_PROGRESS = [
  "NOT_STARTED",
  "IN_PROGRESS",
  "DONE",
] as const;
export const ROADMAP_SOURCE = ["DETERMINISTIC", "AI"] as const;

export const FEATURE_PACKS = ["STARTER", "FULL_AI"] as const;
export type FeaturePack = (typeof FEATURE_PACKS)[number];

/** Every gated feature key (billing/feature-flags + my-features map).
 *  The last five are PLAN-tier features (PHASE2 L1.4) — granted by the tenant's
 *  subscription plan, not the AI packs. */
export const FEATURE_KEYS = [
  "agent1",
  "agent2",
  "agent3",
  "agent4",
  "agent5",
  "chat",
  "jd_generator",
  "career_roadmap",
  "advanced_analytics",
  "custom_branding",
  "sso",
  "api_access",
  "audit_access",
] as const;
export type FeatureKey = (typeof FEATURE_KEYS)[number];

/** The internal subscription plans (PHASE2 L1.4 — no payment gateway yet). */
export const PLANS = ["STARTER", "PROFESSIONAL", "ENTERPRISE"] as const;
export type Plan = (typeof PLANS)[number];

/** Human-readable names + what each gated feature does (for upgrade UI). */
export const FEATURE_META: Record<
  FeatureKey,
  { label: string; description: string; pack: FeaturePack }
> = {
  agent1: {
    label: "Review Assistant",
    description: "AI-drafted performance reviews (Agent 1).",
    pack: "FULL_AI",
  },
  agent2: {
    label: "KPI Intelligence",
    description: "KPI nudges and risk signals for managers (Agent 2).",
    pack: "STARTER",
  },
  agent3: {
    label: "Feedback Summary",
    description: "AI-summarised 360 feedback (Agent 3).",
    pack: "FULL_AI",
  },
  agent4: {
    label: "Succession Analyzer",
    description: "AI succession enrichment (Agent 4).",
    pack: "FULL_AI",
  },
  agent5: {
    label: "Agent 5",
    description: "Advanced agent capability.",
    pack: "FULL_AI",
  },
  chat: {
    label: "AI Chat",
    description: "Read-only natural-language assistant.",
    pack: "STARTER",
  },
  jd_generator: {
    label: "JD Generator",
    description: "AI-generated job descriptions.",
    pack: "FULL_AI",
  },
  career_roadmap: {
    label: "Career Roadmap AI",
    description: "AI-enriched development roadmaps.",
    pack: "FULL_AI",
  },
  // ── PLAN-tier features (PHASE2 L1.4) — granted by the subscription plan. ──
  advanced_analytics: {
    label: "Advanced Analytics",
    description: "Department analytics, calibration and history (Professional+).",
    pack: "FULL_AI",
  },
  custom_branding: {
    label: "Custom Branding",
    description: "Your logo and colors across the workspace (Enterprise).",
    pack: "FULL_AI",
  },
  sso: {
    label: "Enterprise SSO",
    description: "SAML / OIDC single sign-on (Enterprise).",
    pack: "FULL_AI",
  },
  api_access: {
    label: "API Access",
    description: "Programmatic access to the tenant API (Enterprise).",
    pack: "FULL_AI",
  },
  audit_access: {
    label: "Audit Export",
    description: "Extended audit console access (Enterprise).",
    pack: "FULL_AI",
  },
};

export const INTEGRATION_KIND = ["JIRA", "SLACK"] as const;
export type IntegrationKind = (typeof INTEGRATION_KIND)[number];

export const NUDGE_LEVEL = ["CRITICAL", "STANDARD", "SUPPRESSED"] as const;
export type NudgeLevel = (typeof NUDGE_LEVEL)[number];

/** Low-confidence threshold for AI outputs (V0 brief: warn below 0.70). */
export const LOW_CONFIDENCE_THRESHOLD = 0.7;

/** Friendly labels for enum values that aren't already readable. */
export function humanize(value: string): string {
  return value
    .toLowerCase()
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
