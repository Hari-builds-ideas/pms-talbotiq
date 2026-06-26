import { useQuery } from "@tanstack/react-query";
import {
  ClipboardCheck,
  CreditCard,
  FileText,
  GitBranch,
  GraduationCap,
  MessageSquareText,
  Sparkles,
  Target,
  TrendingUp,
  Users,
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { StatCard } from "@/components/StatCard";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth/AuthContext";
import { useChatPanel } from "@/features/chat/ChatPanel";
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
import { ROLE_LABEL, type Role } from "@/lib/enums";
import { formatScore } from "@/lib/format";
import {
  ApprovalsInboxTile,
  LockedFeaturesTile,
  NudgesTile,
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
  ReviewsAwaitingTile,
  TenantHealthTile,
  useMyScore,
} from "./cockpit";

const ACTIVE_REVIEW_STATES = ["DRAFT", "AI_DRAFTING", "PENDING_HUMAN_REVIEW", "EDITING", "APPROVED"];

/**
 * Role-true cockpit. Each role lands on the work that matters to them, composed
 * client-side from the real feature endpoints (no /dashboard endpoint). Real
 * counts, real links, real empty states.
 */
export function DashboardPage() {
  const { me } = useAuth();
  const chat = useChatPanel();
  const role = me?.role;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={role ? `${ROLE_LABEL[role as Role]} workspace` : undefined}
        title={`Good to see you${me?.display ? `, ${me.display.split(" ")[0]}` : ""}`}
        description={descriptionFor(role)}
        actions={
          <Button variant="outline" onClick={chat.toggle}>
            <Sparkles className="h-4 w-4 text-ai" />
            Ask AI
          </Button>
        }
      />

      {role === "EMPLOYEE" ? (
        <EmployeeCockpit />
      ) : role === "ADMIN" ? (
        <AdminCockpit />
      ) : role === "HRBP" ? (
        <HrbpCockpit />
      ) : (
        <ManagerCockpit />
      )}
    </div>
  );
}

function descriptionFor(role?: string): string {
  switch (role) {
    case "EMPLOYEE":
      return "Your goals, review, feedback and development in one place.";
    case "ADMIN":
      return "Tenant health, entitlements and the activity trail.";
    case "HRBP":
      return "Feedback summaries to release, succession coverage and approvals.";
    default:
      return "Your team's risk, reviews to action, and your approval inbox.";
  }
}

// ── Manager ──────────────────────────────────────────────────────────────────
function ManagerCockpit() {
  const { hasFeature } = useAuth();
  const inbox = useQuery({ queryKey: ["approvals", "inbox"], queryFn: approvalsApi.inbox });
  const nudges = useQuery({ queryKey: ["ai", "nudges"], queryFn: aiApi.nudges, enabled: hasFeature("agent2") });
  const reviews = useQuery({ queryKey: ["reviews", "list", { dashboard: true }], queryFn: () => reviewsApi.list({ page_size: 50 }) });

  const pending = inbox.data?.length ?? 0;
  const critical = nudges.data?.filter((n) => n.level === "CRITICAL").length ?? 0;
  const toAction = (reviews.data?.results ?? []).filter((r) => ACTIVE_REVIEW_STATES.includes(r.state)).length;

  // Succession is an HR/Admin tool in the re-weighted surface (RW_BUILD_1 Phase 1.3,
  // D31) — the manager cockpit no longer surfaces a coverage stat or risk tile that
  // links into /succession. Backend VIEW_SUCCESSION for managers is unchanged.
  return (
    <>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label="Pending approvals" value={pending} icon={ClipboardCheck} tone={pending > 0 ? "warning" : "default"} loading={inbox.isLoading} hint={pending > 0 ? "Awaiting your decision" : "Inbox zero"} to="/approvals" />
        <StatCard label="At-risk reports" value={hasFeature("agent2") ? critical : "—"} icon={TrendingUp} tone={critical > 0 ? "danger" : "default"} loading={hasFeature("agent2") && nudges.isLoading} hint={hasFeature("agent2") ? "Flagged by KPI Intelligence" : "Upgrade to surface"} />
        <StatCard label="Reviews to action" value={toAction} icon={FileText} tone={toAction > 0 ? "info" : "default"} loading={reviews.isLoading} hint="Drafting or approval" to="/reviews" />
      </div>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <ReviewsAwaitingTile />
          <NudgesTile />
        </div>
        <div className="space-y-5">
          <ApprovalsInboxTile />
          <LockedFeaturesTile />
        </div>
      </div>
    </>
  );
}

// ── HRBP ─────────────────────────────────────────────────────────────────────
function HrbpCockpit() {
  const { hasFeature } = useAuth();
  const inbox = useQuery({ queryKey: ["approvals", "inbox"], queryFn: approvalsApi.inbox });
  const nudges = useQuery({ queryKey: ["ai", "nudges"], queryFn: aiApi.nudges, enabled: hasFeature("agent2") });
  const summaries = useQuery({ queryKey: ["feedback", "summaries", "review"], queryFn: () => feedbackApi.summariesReview() });
  const succession = useQuery({ queryKey: ["succession", "dashboard"], queryFn: successionApi.dashboard });

  const toRelease = summaries.data?.results.length ?? 0;
  const redRoles = succession.data?.critical_roles.filter((r) => r.coverage_status === "RED").length ?? 0;
  const pending = inbox.data?.length ?? 0;
  const atRisk = nudges.data?.filter((n) => n.level !== "SUPPRESSED").length ?? 0;

  return (
    <>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Summaries to release" value={toRelease} icon={MessageSquareText} tone={toRelease > 0 ? "warning" : "default"} loading={summaries.isLoading} hint="360 feedback (HITL)" to="/feedback" />
        <StatCard label="Coverage gaps" value={redRoles} icon={GitBranch} tone={redRoles > 0 ? "danger" : "success"} loading={succession.isLoading} hint="Critical roles at RED" to="/succession" />
        <StatCard label="Pending approvals" value={pending} icon={ClipboardCheck} tone={pending > 0 ? "warning" : "default"} loading={inbox.isLoading} hint="Awaiting your decision" to="/approvals" />
        <StatCard label="At-risk people" value={hasFeature("agent2") ? atRisk : "—"} icon={TrendingUp} tone={atRisk > 0 ? "danger" : "default"} loading={hasFeature("agent2") && nudges.isLoading} hint="Across your scope" />
      </div>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <FeedbackSummariesTile />
          <SuccessionRiskTile />
        </div>
        <div className="space-y-5">
          <ApprovalsInboxTile />
          <NudgesTile />
        </div>
      </div>
    </>
  );
}

// ── Admin ──────────────────────────────────────────────────────────────────
function AdminCockpit() {
  // Active-user count comes from the DB-aggregated stats endpoint, not a full
  // user-list download — bounded regardless of tenant size.
  const users = useQuery({ queryKey: ["admin", "users", "stats"], queryFn: adminApi.userStats });
  const ent = useQuery({ queryKey: ["billing", "entitlement"], queryFn: billingApi.entitlement });
  const succession = useQuery({ queryKey: ["succession", "dashboard"], queryFn: successionApi.dashboard });

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
        <StatCard label="Critical roles" value={roles} icon={GitBranch} loading={succession.isLoading} hint="Tracked for succession" />
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
function EmployeeCockpit() {
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
          value={score ? formatScore(score.t_score) : "—"}
          icon={TrendingUp}
          tone={score?.risk_status === "CRITICAL" ? "danger" : score?.risk_status === "AT_RISK" ? "warning" : "success"}
          loading={myScore.isLoading}
          hint={score ? `T-score · ${score.risk_status.replace("_", " ").toLowerCase()}` : "Not yet scored"}
        />
        <StatCard label="Feedback requests" value={pendingReq} icon={MessageSquareText} tone={pendingReq > 0 ? "warning" : "default"} loading={requests.isLoading} hint="Awaiting your input" />
        <StatCard label="Review status" value={reviewState ? reviewState.replace(/_/g, " ").toLowerCase() : "—"} icon={FileText} loading={reviews.isLoading} hint="This cycle" />
      </div>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <MyGoalsTile />
        <MyReviewTile />
        <MyFeedbackRequestsTile />
        <MyRoadmapTile />
      </div>
      <div className="rounded-lg border border-dashed border-border bg-card/40 px-4 py-3 text-xs text-muted-foreground">
        <GraduationCap className="mr-1.5 inline h-3.5 w-3.5" />
        This is your self-service view. A dedicated responsive mobile-web surface is a separate build.
      </div>
    </>
  );
}
