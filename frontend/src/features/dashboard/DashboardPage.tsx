import { useQuery } from "@tanstack/react-query";
import { ClipboardCheck, GitBranch, ScrollText, Smartphone, Sparkles, TrendingUp } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { StatCard } from "@/components/StatCard";
import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth/AuthContext";
import { useChatPanel } from "@/features/chat/ChatPanel";
import { approvalsApi, aiApi, successionApi } from "@/lib/api/endpoints";
import { ROLE_LABEL, type Role } from "@/lib/enums";
import {
  ApprovalsInboxTile,
  LockedFeaturesTile,
  NudgesTile,
  SuccessionRiskTile,
} from "./tiles";

/**
 * Role-aware, action-first landing. Composed entirely client-side from the
 * feature endpoints (there is no /dashboard endpoint — open-question #9). It
 * answers: what needs action, what's blocked, what's at risk.
 */
export function DashboardPage() {
  const { me, atLeast } = useAuth();
  const chat = useChatPanel();

  if (me?.role === "EMPLOYEE") return <EmployeeNotice />;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={me ? `${ROLE_LABEL[me.role as Role]} workspace` : undefined}
        title={`Good to see you${me?.display ? `, ${me.display.split(" ")[0]}` : ""}`}
        description="Here's what needs your attention across approvals, talent risk and succession."
        actions={
          <Button variant="outline" onClick={chat.toggle}>
            <Sparkles className="h-4 w-4 text-ai" />
            Ask AI
          </Button>
        }
      />

      <StatStrip />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <ApprovalsInboxTile />
          <NudgesTile />
        </div>
        <div className="space-y-5">
          {atLeast("MANAGER") && <SuccessionRiskTile />}
          <LockedFeaturesTile />
        </div>
      </div>
    </div>
  );
}

function StatStrip() {
  const { hasFeature, me } = useAuth();
  const inbox = useQuery({ queryKey: ["approvals", "inbox"], queryFn: approvalsApi.inbox });
  const nudges = useQuery({
    queryKey: ["ai", "nudges"],
    queryFn: aiApi.nudges,
    enabled: hasFeature("agent2"),
  });
  const succession = useQuery({ queryKey: ["succession", "dashboard"], queryFn: successionApi.dashboard });

  const pending = inbox.data?.length ?? 0;
  const critical = nudges.data?.filter((n) => n.level === "CRITICAL").length ?? 0;
  const redRoles = succession.data?.critical_roles.filter((r) => r.coverage_status === "RED").length ?? 0;
  const activeRoles = succession.data?.critical_roles.length ?? 0;

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <StatCard
        label="Pending approvals"
        value={pending}
        icon={ClipboardCheck}
        tone={pending > 0 ? "warning" : "default"}
        loading={inbox.isLoading}
        hint={pending > 0 ? "Awaiting your decision" : "Inbox zero"}
      />
      <StatCard
        label="At-risk reports"
        value={hasFeature("agent2") ? critical : "—"}
        icon={TrendingUp}
        tone={critical > 0 ? "danger" : "default"}
        loading={hasFeature("agent2") && nudges.isLoading}
        hint={hasFeature("agent2") ? "Flagged critical by KPI Intelligence" : "Upgrade to surface"}
      />
      <StatCard
        label="Coverage gaps"
        value={redRoles}
        icon={GitBranch}
        tone={redRoles > 0 ? "danger" : "success"}
        loading={succession.isLoading}
        hint={`${activeRoles} critical role${activeRoles === 1 ? "" : "s"} tracked`}
      />
      <StatCard
        label="Plan"
        value={me?.role === "ADMIN" ? <PlanValue /> : ROLE_LABEL[me?.role as Role]}
        icon={ScrollText}
        tone="info"
        hint={me?.role === "ADMIN" ? "Manage in Entitlements" : "Your access level"}
      />
    </div>
  );
}

function PlanValue() {
  const { features } = useAuth();
  const fullAi = features?.agent1 && features?.jd_generator;
  return <span className="text-xl">{fullAi ? "Full AI" : "Starter"}</span>;
}

function EmployeeNotice() {
  return (
    <div className="space-y-6">
      <PageHeader title="Admin Hub" description="The desktop Admin Hub is built for management and configuration." />
      <EmptyState
        icon={Smartphone}
        title="Self-service lives on mobile-web"
        description="Your goals, reviews, feedback and career roadmap are available on the responsive self-service surface (a separate build). The Admin Hub is for managers, HRBPs and admins."
      />
    </div>
  );
}
