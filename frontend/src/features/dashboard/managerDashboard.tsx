import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ClipboardCheck, Megaphone, Radar, Smile, Target, TrendingUp, Users } from "lucide-react";
import { DashboardKpiCard, DashboardSection, ScoreDonut, type DonutBand } from "./widgets";
import { StatusBadge } from "@/components/StatusBadge";
import { PersonName } from "@/components/PersonName";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { LinesSkeleton } from "@/components/Skeletons";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/auth/AuthContext";
import { useDirectory } from "@/lib/hooks/useDirectory";
import {
  aiApi,
  approvalsApi,
  checkinsApi,
  cyclesApi,
  feedbackApi,
  goalsApi,
  reviewsApi,
} from "@/lib/api/endpoints";
import { ROLE_LABEL, type Role } from "@/lib/enums";
import { formatRelative } from "@/lib/format";

const ACTIVE_REVIEW_STATES = ["DRAFT", "AI_DRAFTING", "PENDING_HUMAN_REVIEW", "EDITING", "APPROVED"];

/**
 * Manager dashboard — the TalbotIQ mockup composition wired to REAL, team-scoped
 * endpoints. Honest labels throughout: performance is shown as the real T-score
 * (50 = cohort average) + risk bands, never a fabricated 1–5 rating or %. Tiles
 * with no real source degrade to honest empty states.
 */
export function ManagerDashboard() {
  const { me, hasFeature } = useAuth();
  const { roleOf } = useDirectory();

  // Cycle is derived from the caller's goals (managers can't list cycles).
  const goalsQ = useQuery({ queryKey: ["goals", "dash"], queryFn: () => goalsApi.list({ page_size: 100 }) });
  const cycleId = goalsQ.data?.results?.[0]?.cycle;

  const scoresQ = useQuery({
    queryKey: ["cycles", "scores", cycleId],
    queryFn: () => cyclesApi.scores(cycleId!),
    enabled: Boolean(cycleId),
  });
  const reviewsQ = useQuery({ queryKey: ["reviews", "list", { dashboard: true }], queryFn: () => reviewsApi.list({ page_size: 50 }) });
  const inboxQ = useQuery({ queryKey: ["approvals", "inbox"], queryFn: approvalsApi.inbox });
  const nudgesQ = useQuery({ queryKey: ["ai", "nudges"], queryFn: aiApi.nudges, enabled: hasFeature("agent2") });
  const checkinsQ = useQuery({ queryKey: ["checkins", "team"], queryFn: checkinsApi.team });
  const staleQ = useQuery({ queryKey: ["ai", "stale-goals"], queryFn: aiApi.staleGoals });
  const reqsQ = useQuery({ queryKey: ["feedback", "requests", "mine"], queryFn: feedbackApi.requestsMine });

  // ── Derived, real aggregates (team = subtree, excluding self) ──────────────
  const team = (scoresQ.data ?? []).filter((s) => s.employee !== me?.id);
  const scored = team.length;
  const meanT = scored ? team.reduce((a, s) => a + Number(s.t_score), 0) / scored : null;
  const dist = { ON_TRACK: 0, AT_RISK: 0, CRITICAL: 0 } as Record<string, number>;
  team.forEach((s) => { dist[s.risk_status] = (dist[s.risk_status] ?? 0) + 1; });

  const reviews = reviewsQ.data?.results ?? [];
  const finalized = reviews.filter((r) => r.state === "FINALIZED").length;
  const totalReviews = reviews.length;
  const activeReviews = reviews.filter((r) => ACTIVE_REVIEW_STATES.includes(r.state));

  const allGoals = goalsQ.data?.results ?? [];
  const activeGoals = allGoals.filter((g) => g.status === "ACTIVE" || g.status === "ACHIEVED");
  const staleCount = staleQ.data?.stale?.length ?? 0;
  const onTrack = Math.max(0, activeGoals.length - staleCount);
  const onTrackPct = activeGoals.length ? Math.round((onTrack / activeGoals.length) * 100) : null;

  const moods = (checkinsQ.data ?? []).map((c) => c.mood).filter((m): m is number => typeof m === "number");
  const moodAvg = moods.length ? moods.reduce((a, b) => a + b, 0) / moods.length : null;

  const atRisk = hasFeature("agent2") ? (nudgesQ.data ?? []).filter((n) => n.level !== "SUPPRESSED").length : null;
  const pendingReqs = (reqsQ.data ?? []).filter((r) => r.status === "PENDING").length;

  // Per-employee KPI attainment (REAL recorded progress): how many of their KPIs
  // meet target (direction-aware) over total KPIs. Reflects recorded actuals, not
  // goal status — so it shows real numbers, never 0/N for people with progress.
  const kpiByEmp = new Map<string, { onTarget: number; total: number }>();
  for (const g of allGoals) {
    for (const k of g.kpis ?? []) {
      const e = kpiByEmp.get(g.employee) ?? { onTarget: 0, total: 0 };
      e.total += 1;
      const actual = k.latest_actual == null ? null : Number(k.latest_actual);
      const target = Number(k.target_value);
      if (actual != null && (k.direction === "DECREASING" ? actual <= target : actual >= target)) {
        e.onTarget += 1;
      }
      kpiByEmp.set(g.employee, e);
    }
  }

  const bands: DonutBand[] = [
    { key: "on", label: "On track", value: dist.ON_TRACK, color: "hsl(var(--success))" },
    { key: "at", label: "At risk", value: dist.AT_RISK, color: "hsl(var(--warning))" },
    { key: "cr", label: "Critical", value: dist.CRITICAL, color: "hsl(var(--danger))" },
  ];

  return (
    <div className="space-y-5">
      {/* ── 5 KPI cards ─────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <DashboardKpiCard
          label="Team avg score"
          value={meanT != null ? meanT.toFixed(1) : "—"}
          hint="T-score · 50 = cohort average"
          loading={scoresQ.isLoading || goalsQ.isLoading}
        />
        <DashboardKpiCard
          label="Goals on track"
          value={onTrackPct != null ? `${onTrackPct}%` : "—"}
          hint={activeGoals.length ? `${onTrack} of ${activeGoals.length} active goals on pace` : "No active goals"}
          valueTone={onTrackPct != null && onTrackPct < 60 ? "warning" : "default"}
          loading={goalsQ.isLoading || staleQ.isLoading}
        />
        <DashboardKpiCard
          label="Reviews completed"
          value={`${finalized} / ${totalReviews || 0}`}
          hint={totalReviews ? `${Math.round((finalized / totalReviews) * 100)}% finalized` : "No reviews in scope"}
          progress={totalReviews ? (finalized / totalReviews) * 100 : 0}
          loading={reviewsQ.isLoading}
          to="/reviews"
        />
        <DashboardKpiCard
          label="Team mood"
          value={moodAvg != null ? `${moodAvg.toFixed(1)} / 5` : "—"}
          hint={moodAvg != null ? "Check-in mood average (1–5)" : "No check-ins yet"}
          loading={checkinsQ.isLoading}
          to="/checkins"
        />
        <DashboardKpiCard
          label="At-risk employees"
          value={atRisk ?? "—"}
          valueTone={atRisk && atRisk > 0 ? "danger" : "default"}
          hint={hasFeature("agent2") ? "Flagged by KPI Intelligence" : "Upgrade to surface"}
          loading={hasFeature("agent2") && nudgesQ.isLoading}
        />
      </div>

      {/* ── Performance Overview + My Tasks ─────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <DashboardSection title="Performance overview" icon={TrendingUp} className="lg:col-span-2">
          {scoresQ.isLoading ? (
            <LinesSkeleton lines={5} />
          ) : scoresQ.isError ? (
            <ErrorState error={scoresQ.error} onRetry={() => scoresQ.refetch()} compact />
          ) : scored === 0 ? (
            <EmptyState compact icon={TrendingUp} title="No scored team members yet" description="Once your team's scores are computed for the cycle, the distribution appears here." />
          ) : (
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
              <div>
                <p className="text-sm text-muted-foreground">Average team T-score</p>
                <p className="mt-1 text-3xl font-bold tabular-nums text-foreground">{meanT!.toFixed(1)}</p>
                <p className="mt-1 text-xs text-muted-foreground">50 = cohort average · across {scored} scored {scored === 1 ? "member" : "members"}</p>
                <p className="mt-4 rounded-lg bg-secondary/60 px-3 py-2 text-xs text-muted-foreground">
                  A per-cycle trend line appears once more than one cycle has been scored.
                </p>
              </div>
              <div>
                <p className="mb-3 text-sm text-muted-foreground">Score distribution (by risk band)</p>
                <ScoreDonut bands={bands} centerValue={scored} centerLabel={scored === 1 ? "Member" : "Members"} />
              </div>
            </div>
          )}
        </DashboardSection>

        <DashboardSection title="My tasks" icon={ClipboardCheck} to="/approvals" toLabel="Inbox">
          <TasksRail
            loading={inboxQ.isLoading || reviewsQ.isLoading}
            tasks={[
              ...(inboxQ.data ?? []).map((i) => ({
                id: `ap-${i.id}`,
                label: `Approve ${i.artifact_type.replace(/_/g, " ").toLowerCase()}`,
                sub: i.due_at ? `Due ${formatRelative(i.due_at)}` : "Awaiting your decision",
                href: "/approvals",
                priority: "high" as const,
              })),
              ...activeReviews.slice(0, 4).map((r) => ({
                id: `rv-${r.id}`,
                label: "Action a performance review",
                sub: r.employee_name ?? "Drafting / approval",
                href: `/reviews/${r.id}`,
                priority: "med" as const,
              })),
              ...Array.from({ length: pendingReqs ? 1 : 0 }).map(() => ({
                id: "fb",
                label: `Give feedback (${pendingReqs} request${pendingReqs === 1 ? "" : "s"})`,
                sub: "360 feedback awaiting you",
                href: "/feedback",
                priority: "med" as const,
              })),
              ...(staleCount ? [{ id: "stale", label: `Nudge ${staleCount} stale goal${staleCount === 1 ? "" : "s"}`, sub: "No update in a while", href: "/goals", priority: "low" as const }] : []),
            ]}
          />
        </DashboardSection>
      </div>

      {/* ── Team table · Competency · Announcements ─────────────────────────── */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-4">
        <DashboardSection title="Team performance" icon={Users} to="/analytics" className="lg:col-span-2">
          {scoresQ.isLoading ? (
            <LinesSkeleton lines={5} />
          ) : scoresQ.isError ? (
            <ErrorState error={scoresQ.error} onRetry={() => scoresQ.refetch()} compact />
          ) : team.length === 0 ? (
            <EmptyState compact icon={Users} title="No team scores yet" description="Your reports' scores for the cycle appear here." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <th className="pb-2 pr-3 font-semibold">Employee</th>
                    <th className="pb-2 pr-3 font-semibold">Role</th>
                    <th className="pb-2 pr-3 text-right font-semibold">T-score</th>
                    <th className="pb-2 pr-3 font-semibold">Status</th>
                    <th className="pb-2 text-right font-semibold">KPIs on target</th>
                  </tr>
                </thead>
                <tbody>
                  {team.map((s) => {
                    const kp = kpiByEmp.get(s.employee);
                    const role = roleOf(s.employee);
                    return (
                      <tr key={s.employee} className="border-b border-border last:border-0 hover:bg-secondary/40">
                        <td className="py-2.5 pr-3">
                          <Link to={`/people/${s.employee}`} className="hover:underline">
                            <PersonName id={s.employee} withAvatar className="font-medium" />
                          </Link>
                        </td>
                        <td className="py-2.5 pr-3 text-muted-foreground">{role ? ROLE_LABEL[role as Role] : "—"}</td>
                        <td className="py-2.5 pr-3 text-right font-semibold tabular-nums">{Number(s.t_score).toFixed(1)}</td>
                        <td className="py-2.5 pr-3"><StatusBadge status={s.risk_status} dot /></td>
                        <td className="py-2.5 text-right tabular-nums text-muted-foreground">{kp ? `${kp.onTarget}/${kp.total}` : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </DashboardSection>

        <DashboardSection title="Team competency" icon={Radar}>
          <EmptyState
            compact
            icon={Radar}
            title="Not available yet"
            description="Competency scoring isn't part of the data model yet, so this stays empty rather than showing invented numbers."
          />
        </DashboardSection>

        <DashboardSection title="Announcements" icon={Megaphone}>
          <AnnouncementsCard cycleActive={Boolean(cycleId)} />
        </DashboardSection>
      </div>
    </div>
  );
}

// ── My Tasks rail ────────────────────────────────────────────────────────────
type Task = { id: string; label: string; sub: string; href: string; priority: "high" | "med" | "low" };
const PRIO_ORDER = { high: 0, med: 1, low: 2 };
const PRIO_BADGE: Record<Task["priority"], { label: string; variant: "danger" | "warning" | "muted" }> = {
  high: { label: "High", variant: "danger" },
  med: { label: "Medium", variant: "warning" },
  low: { label: "Low", variant: "muted" },
};

function TasksRail({ tasks, loading }: { tasks: Task[]; loading: boolean }) {
  if (loading) return <LinesSkeleton lines={4} />;
  const sorted = [...tasks].sort((a, b) => PRIO_ORDER[a.priority] - PRIO_ORDER[b.priority]).slice(0, 6);
  if (sorted.length === 0) {
    return <EmptyState compact icon={ClipboardCheck} title="You're all caught up" description="Approvals, reviews and feedback you owe appear here." />;
  }
  return (
    <ul className="divide-y divide-border">
      {sorted.map((t) => {
        const b = PRIO_BADGE[t.priority];
        return (
          <li key={t.id} className="py-2.5 first:pt-0 last:pb-0">
            <Link to={t.href} className="flex items-center justify-between gap-3 hover:underline">
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-foreground">{t.label}</span>
                <span className="block truncate text-2xs text-muted-foreground">{t.sub}</span>
              </span>
              <Badge variant={b.variant}>{b.label}</Badge>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

// ── Announcements (real active-cycle status, else empty) ──────────────────────
// N4: a single REAL active-cycle status line derived from the caller's own cycle
// (no feedback-cycle list call — managers may lack that capability). Never static
// marketing copy.
function AnnouncementsCard({ cycleActive }: { cycleActive: boolean }) {
  if (!cycleActive) {
    return <EmptyState compact icon={Smile} title="Nothing new" description="Active cycles and feedback windows show up here." />;
  }
  return (
    <ul className="space-y-3">
      <li className="rounded-lg bg-secondary/50 p-3">
        <p className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
          <Target className="h-4 w-4 text-primary" />
          Performance cycle is active
        </p>
        <p className="mt-1 text-xs text-muted-foreground">Goals and reviews for the current cycle are open.</p>
      </li>
    </ul>
  );
}
