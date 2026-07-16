import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ClipboardCheck,
  GitBranch,
  Inbox,
  Lock,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";
import { Panel } from "@/components/Panel";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { StatusBadge } from "@/components/StatusBadge";
import { PersonName } from "@/components/PersonName";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { LinesSkeleton } from "@/components/Skeletons";
import { approvalsApi, aiApi, successionApi } from "@/lib/api/endpoints";
import { useAuth } from "@/lib/auth/AuthContext";
import { FEATURE_META, type FeatureKey, humanize } from "@/lib/enums";
import { formatRelative, isOverdue } from "@/lib/format";
import { cn } from "@/lib/utils";

// ---- Approvals inbox -------------------------------------------------------

export function ApprovalsInboxTile() {
  const q = useQuery({ queryKey: ["approvals", "inbox"], queryFn: approvalsApi.inbox });
  return (
    <Panel
      title="Approval inbox"
      icon={ClipboardCheck}
      to="/approvals"
      scroll
      aside={
        q.data && q.data.length > 0 ? (
          <Badge variant="warning">{q.data.length}</Badge>
        ) : undefined
      }
    >
      {q.isLoading ? (
        <LinesSkeleton lines={3} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} compact />
      ) : q.data && q.data.length > 0 ? (
        <ul className="divide-y divide-border">
          {q.data.map((item) => {
            const overdue = isOverdue(item.due_at);
            return (
              <li key={item.id} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {humanize(item.artifact_type)} approval
                    <span className="ml-1.5 font-normal text-muted-foreground">
                      · step {item.order}
                    </span>
                  </p>
                  <p className="text-2xs text-muted-foreground">
                    Due {formatRelative(item.due_at)}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  {item.escalated && <Badge variant="warning">Escalated</Badge>}
                  {overdue && <Badge variant="danger">Overdue</Badge>}
                  <StatusBadge status={item.status} />
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <EmptyState
          compact
          icon={Inbox}
          title="Inbox zero"
          description="No approval steps are waiting on you right now."
        />
      )}
    </Panel>
  );
}

// ---- KPI nudges ------------------------------------------------------------

const NUDGE_TONE: Record<string, string> = {
  CRITICAL: "border-l-danger bg-danger-subtle/40",
  STANDARD: "border-l-warning bg-warning-subtle/40",
  SUPPRESSED: "border-l-border bg-muted/40",
};

export function NudgesTile() {
  const { hasFeature } = useAuth();
  const enabled = hasFeature("agent2");
  const q = useQuery({
    queryKey: ["ai", "nudges"],
    queryFn: aiApi.nudges,
    enabled,
  });

  // One row per person (keep the worst severity), worst-first, capped — the raw list is
  // the whole tenant for HRBP/Admin and read as an endless wall (BUGS_FOUND #8).
  const rank: Record<string, number> = { CRITICAL: 0, STANDARD: 1, SUPPRESSED: 2 };
  const byPerson = new Map<string, NonNullable<typeof q.data>[number]>();
  for (const n of q.data ?? []) {
    const cur = byPerson.get(n.employee);
    if (!cur || (rank[n.level] ?? 9) < (rank[cur.level] ?? 9)) byPerson.set(n.employee, n);
  }
  const deduped = [...byPerson.values()].sort(
    (a, b) => (rank[a.level] ?? 9) - (rank[b.level] ?? 9),
  );
  const shown = deduped.slice(0, 5);
  const more = deduped.length - shown.length;

  return (
    <Panel
      title="KPI nudges"
      icon={TrendingUp}
      scroll
      aside={<Badge variant="ai" className="gap-1"><Sparkles className="h-3 w-3" />Agent 2</Badge>}
    >
      {!enabled ? (
        <EmptyState compact icon={Lock} title="KPI Intelligence is locked" description="Upgrade to surface team risk nudges." />
      ) : q.isLoading ? (
        <LinesSkeleton lines={3} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} compact />
      ) : shown.length > 0 ? (
        <ul className="space-y-2">
          {shown.map((n) => (
            <li
              key={n.employee}
              className={cn("rounded-md border-l-2 px-3 py-2", NUDGE_TONE[n.level] ?? NUDGE_TONE.STANDARD)}
            >
              <Link to={`/people/${n.employee}`} className="block hover:opacity-90">
                <div className="flex items-center justify-between gap-2">
                  <PersonName id={n.employee} withAvatar className="text-sm font-medium" />
                  <StatusBadge status={n.level} />
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{n.message}</p>
              </Link>
            </li>
          ))}
          {more > 0 && (
            <li className="px-3 pt-1 text-xs text-muted-foreground">
              +{more} more person{more === 1 ? "" : "s"} flagged at risk
            </li>
          )}
        </ul>
      ) : (
        <EmptyState compact icon={TrendingUp} title="No nudges" description="No one on your team is flagged at risk this cycle." />
      )}
    </Panel>
  );
}

// ---- Stale goals (RW_BUILD_5 quick win) ------------------------------------

/**
 * A manager/HR tile: ACTIVE goals in the caller's scope with no KPI progress in
 * ~30 days (deterministic, scope-bound) + ONE advisory AI follow-up suggestion.
 * READ-ONLY — it surfaces and suggests; the manager acts via a check-in. The
 * endpoint always returns the list (the suggestion degrades to null with no AI),
 * so there's no AI-unavailable error state to special-case here.
 */
export function StaleGoalsTile() {
  const q = useQuery({ queryKey: ["ai", "stale-goals"], queryFn: aiApi.staleGoals });
  const stale = q.data?.stale ?? [];

  return (
    <Panel
      title="Stale goals"
      icon={Target}
      to="/checkins"
      toLabel="Start a check-in"
      scroll
      aside={<Badge variant="ai" className="gap-1"><Sparkles className="h-3 w-3" />AI</Badge>}
    >
      {q.isLoading ? (
        <LinesSkeleton lines={3} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} compact />
      ) : stale.length === 0 ? (
        <EmptyState compact icon={Target} title="No stale goals" description="Your team's active goals all have recent progress." />
      ) : (
        <div className="space-y-3">
          <ul className="space-y-2">
            {stale.slice(0, 6).map((s, i) => (
              <li key={`${s.goal}-${i}`} className="rounded-md border-l-2 border-l-warning bg-warning-subtle/40 px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{s.goal}</span>
                  <Badge variant="muted" className="shrink-0">
                    {s.days_stale != null ? `${s.days_stale}d stale` : "no progress yet"}
                  </Badge>
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">{s.employee}</p>
              </li>
            ))}
            {stale.length > 6 && (
              <li className="text-xs text-muted-foreground">…and {stale.length - 6} more</li>
            )}
          </ul>
          {q.data?.suggestion && (
            <div className="rounded-md border border-ai/30 bg-ai-subtle/40 p-2.5 text-xs">
              <p className="flex items-center gap-1.5 font-semibold text-ai">
                <Sparkles className="h-3 w-3" /> Suggested follow-up
              </p>
              <p className="mt-1 text-foreground">{q.data.suggestion}</p>
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

// ---- Succession risks ------------------------------------------------------

export function SuccessionRiskTile() {
  const q = useQuery({ queryKey: ["succession", "dashboard"], queryFn: successionApi.dashboard });
  const roles = q.data?.critical_roles ?? [];
  const atRisk = [...roles].sort((a, b) => coverageRank(a.coverage_status) - coverageRank(b.coverage_status));

  return (
    <Panel title="Succession risk" icon={GitBranch} to="/succession" scroll>
      {q.isLoading ? (
        <LinesSkeleton lines={3} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} compact />
      ) : atRisk.length > 0 ? (
        <ul className="divide-y divide-border">
          {atRisk.slice(0, 5).map((r) => (
            <li key={r.id} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{r.name}</p>
                <p className="text-2xs text-muted-foreground">
                  {humanize(r.criticality)} · knowledge risk {humanize(r.knowledge_risk)}
                </p>
              </div>
              <StatusBadge status={r.coverage_status} dot />
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState compact icon={GitBranch} title="No critical roles" description="Mark critical roles to track succession coverage." />
      )}
    </Panel>
  );
}

function coverageRank(c: string): number {
  return c === "RED" ? 0 : c === "AMBER" ? 1 : 2;
}

// ---- Locked features upsell ------------------------------------------------

export function LockedFeaturesTile() {
  const { features, me } = useAuth();
  if (!features) return null;
  const locked = (Object.keys(features) as FeatureKey[]).filter(
    (k) => !features[k] && FEATURE_META[k]?.pack === "FULL_AI",
  );
  if (locked.length === 0) return null;
  const isAdmin = me?.role === "ADMIN";

  return (
    <Panel
      title="Unlock with Full AI"
      icon={Sparkles}
      aside={<Badge variant="premium" className="gap-1"><Lock className="h-3 w-3" />Premium</Badge>}
    >
      <p className="mb-3 text-xs text-muted-foreground">
        {locked.length} premium {locked.length === 1 ? "capability is" : "capabilities are"} locked on your current plan.
      </p>
      <ul className="mb-4 space-y-1.5">
        {locked.slice(0, 4).map((k) => (
          <li key={k} className="flex items-center gap-2 text-sm">
            <Lock className="h-3.5 w-3.5 text-premium" />
            <span className="font-medium">{FEATURE_META[k].label}</span>
            <span className="truncate text-2xs text-muted-foreground">{FEATURE_META[k].description}</span>
          </li>
        ))}
      </ul>
      {isAdmin ? (
        <Button asChild variant="premium" size="sm" className="w-full">
          <Link to="/admin/billing"><Sparkles className="h-4 w-4" />Upgrade to Full AI</Link>
        </Button>
      ) : (
        <p className="flex items-center gap-1.5 text-2xs text-muted-foreground">
          <AlertTriangle className="h-3.5 w-3.5" />
          Ask your workspace admin to upgrade.
        </p>
      )}
    </Panel>
  );
}
