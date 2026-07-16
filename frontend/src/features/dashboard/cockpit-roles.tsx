import { useQuery } from "@tanstack/react-query";
import {
  ClipboardCheck,
  CreditCard,
  FileText,
  GitBranch,
  GraduationCap,
  MessageSquareText,
  Target,
  TrendingUp,
  Users,
} from "lucide-react";
import { StatCard } from "@/components/StatCard";
import { useAuth } from "@/lib/auth/AuthContext";
import { isHiddenInV1, V1_HIDE_TSCORE } from "@/app/v1";
import { performanceLabel } from "@/components/ScoreBar";
import {
  adminApi,
  approvalsApi,
  aiApi,
  billingApi,
  feedbackApi,
  goalsApi,
  reviewsApi,
  successionApi,
} from "@/lib/api/endpoints";
import { formatScore } from "@/lib/format";
import {
  ApprovalsInboxTile,
  LockedFeaturesTile,
  NudgesTile,
  StaleGoalsTile,
  SuccessionRiskTile,
} from "./tiles";
import {
  EntitlementTile,
  FeedbackSummariesTile,
  MyFeedbackRequestsTile,
  MyGoalsTile,
  MyReviewTile,
  MyRoadmapTile,
  RecentAuditTile,
  TenantHealthTile,
  useMyScore,
} from "./cockpit";

// ── HRBP ─────────────────────────────────────────────────────────────────────
export function HrbpCockpit() {
  const { hasFeature } = useAuth();
  const inbox = useQuery({ queryKey: ["approvals", "inbox"], queryFn: approvalsApi.inbox });
  const nudges = useQuery({ queryKey: ["ai", "nudges"], queryFn: aiApi.nudges, enabled: hasFeature("agent2") });
  const summaries = useQuery({ queryKey: ["feedback", "summaries", "review"], queryFn: () => feedbackApi.summariesReview() });
  // v1: succession hidden — don't even fetch it (query retained for v2 via app/v1.ts).
  const succession = useQuery({ queryKey: ["succession", "dashboard"], queryFn: successionApi.dashboard, enabled: !isHiddenInV1("/succession") });

  const toRelease = summaries.data?.results.length ?? 0;
  const redRoles = succession.data?.critical_roles.filter((r) => r.coverage_status === "RED").length ?? 0;
  const pending = inbox.data?.length ?? 0;
  const atRisk = nudges.data?.filter((n) => n.level !== "SUPPRESSED").length ?? 0;

  return (
    <>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Summaries to release" value={toRelease} icon={MessageSquareText} tone={toRelease > 0 ? "warning" : "default"} loading={summaries.isLoading} hint="360 feedback (HITL)" to="/feedback" />
        {/* v1: "Coverage gaps" (succession) hidden — kept for v2 (app/v1.ts). */}
        {!isHiddenInV1("/succession") && (
          <StatCard label="Coverage gaps" value={redRoles} icon={GitBranch} tone={redRoles > 0 ? "danger" : "success"} loading={succession.isLoading} hint="Critical roles at RED" to="/succession" />
        )}
        <StatCard label="Pending approvals" value={pending} icon={ClipboardCheck} tone={pending > 0 ? "warning" : "default"} loading={inbox.isLoading} hint="Awaiting your decision" to="/approvals" />
        <StatCard label="At-risk people" value={hasFeature("agent2") ? atRisk : "—"} icon={TrendingUp} tone={atRisk > 0 ? "danger" : "default"} loading={hasFeature("agent2") && nudges.isLoading} hint="Across your scope" />
      </div>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <FeedbackSummariesTile />
          {/* v1: succession-risk tile hidden — kept for v2 (app/v1.ts). */}
          {!isHiddenInV1("/succession") && <SuccessionRiskTile />}
        </div>
        <div className="space-y-5">
          <ApprovalsInboxTile />
          <NudgesTile />
          <StaleGoalsTile />
        </div>
      </div>
    </>
  );
}

// ── Admin ──────────────────────────────────────────────────────────────────
export function AdminCockpit() {
  const users = useQuery({ queryKey: ["admin", "users", "stats"], queryFn: adminApi.userStats });
  const ent = useQuery({ queryKey: ["billing", "entitlement"], queryFn: billingApi.entitlement });
  const succession = useQuery({ queryKey: ["succession", "dashboard"], queryFn: successionApi.dashboard, enabled: !isHiddenInV1("/succession") });

  const activeUsers = users.data?.active ?? 0;
  const seats = ent.data?.seat_count ?? 0;
  const tier = ent.data?.tier_label ?? "—";
  const roles = succession.data?.critical_roles.length ?? 0;

  return (
    <>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Active users" value={activeUsers} icon={Users} loading={users.isLoading} hint={`${seats} seats`} />
        <StatCard label="Plan" value={tier} icon={CreditCard} tone={tier === "Full AI" ? "success" : "info"} loading={ent.isLoading} hint="Entitlements" />
        <StatCard label="Seats" value={seats} icon={Users} loading={ent.isLoading} hint="Billed independently" />
        {/* v1: "Critical roles" (succession) hidden — kept for v2 (app/v1.ts). */}
        {!isHiddenInV1("/succession") && (
          <StatCard label="Critical roles" value={roles} icon={GitBranch} loading={succession.isLoading} hint="Tracked for succession" />
        )}
      </div>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <RecentAuditTile />
          <ApprovalsInboxTile />
        </div>
        <div className="space-y-5">
          <TenantHealthTile />
          <EntitlementTile />
          <LockedFeaturesTile />
        </div>
      </div>
    </>
  );
}

// ── Employee ─────────────────────────────────────────────────────────────────
export function EmployeeCockpit() {
  const goals = useQuery({ queryKey: ["goals", "mine"], queryFn: () => goalsApi.list({ page_size: 50 }) });
  const reviews = useQuery({ queryKey: ["reviews", "mine"], queryFn: () => reviewsApi.list({ page_size: 20 }) });
  const requests = useQuery({ queryKey: ["feedback", "requests", "mine"], queryFn: feedbackApi.requestsMine });
  // Derive the cycle from the employee's own goals (they can't list cycles).
  const cycleId = goals.data?.results[0]?.cycle;
  const myScore = useMyScore(cycleId);

  const goalCount = goals.data?.results.length ?? 0;
  const reviewState = reviews.data?.results[0]?.state;
  const pendingReq = (requests.data ?? []).filter((r) => r.status === "PENDING").length;
  const score = myScore.data;

  return (
    <>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="My goals" value={goalCount} icon={Target} loading={goals.isLoading} hint="Active cycle" />
        <StatCard
          label="My performance"
          value={score ? performanceLabel(score.risk_status) : "—"}
          icon={TrendingUp}
          tone={score?.risk_status === "CRITICAL" ? "danger" : score?.risk_status === "AT_RISK" ? "warning" : "success"}
          loading={myScore.isLoading}
          hint={score ? (V1_HIDE_TSCORE ? "How your goals are tracking this cycle" : `Score ${formatScore(score.t_score)}/100 · 50 = team average`) : "Not yet scored"}
        />
        <StatCard label="Feedback requests" value={pendingReq} icon={MessageSquareText} tone={pendingReq > 0 ? "warning" : "default"} loading={requests.isLoading} hint="Awaiting your input" />
        <StatCard label="Review status" value={reviewState ? reviewState.replace(/_/g, " ").toLowerCase() : "—"} icon={FileText} loading={reviews.isLoading} hint="This cycle" />
      </div>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <MyGoalsTile />
        <MyReviewTile />
        <MyFeedbackRequestsTile />
        {/* v1: career roadmap tile hidden — kept for v2 (app/v1.ts). */}
        {!isHiddenInV1("/career") && <MyRoadmapTile />}
      </div>
      <div className="rounded-lg border border-dashed border-border bg-card/40 px-4 py-3 text-xs text-muted-foreground">
        <GraduationCap className="mr-1.5 inline h-3.5 w-3.5" />
        This is your self-service view. A dedicated responsive mobile-web surface is a separate build.
      </div>
    </>
  );
}
