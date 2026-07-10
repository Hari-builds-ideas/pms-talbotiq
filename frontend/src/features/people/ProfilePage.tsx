import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, FileText, GraduationCap, Target, TrendingUp } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { DashboardSection } from "@/features/dashboard/widgets";
import { TrendChart } from "@/components/TrendChart";
import { AttainmentBar } from "@/components/AttainmentBar";
import { ProgressBar } from "@/components/ProgressBar";
import { StatusBadge } from "@/components/StatusBadge";
import { ScoreBar, performanceLabel, T_SCORE_PLAIN } from "@/components/ScoreBar";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { LinesSkeleton } from "@/components/Skeletons";
import { analyticsApi, careerApi, goalsApi, orgApi, reviewsApi } from "@/lib/api/endpoints";
import { ROLE_LABEL, type Role } from "@/lib/enums";
import { initials } from "@/lib/format";
import { cn } from "@/lib/utils";
import { V1_HIDE_TSCORE } from "@/app/v1";
import { personProgress, progressStatus, PROGRESS_TEXT_CLASS } from "@/lib/goalProgress";

/**
 * Employee profile — a read-only growth narrative composed ENTIRELY from existing,
 * scope-bound endpoints (org card, individual analytics trend, their goals,
 * reviews and roadmap). No new backend, no new data; honest T-score throughout.
 * Out-of-scope ids 404 server-side and render as a friendly empty/error state.
 */
export function ProfilePage() {
  const { id = "" } = useParams();

  const personQ = useQuery({ queryKey: ["org", "person", id], queryFn: () => orgApi.person(id), enabled: Boolean(id) });
  const analyticsQ = useQuery({ queryKey: ["analytics", "individual", id], queryFn: () => analyticsApi.individual(id), enabled: Boolean(id) });
  const goalsQ = useQuery({ queryKey: ["goals", "person", id], queryFn: () => goalsApi.list({ employee: id, page_size: 50 }), enabled: Boolean(id) });
  const reviewsQ = useQuery({ queryKey: ["reviews", "person", id], queryFn: () => reviewsApi.list({ employee: id, page_size: 20 }), enabled: Boolean(id) });
  const roadmapQ = useQuery({ queryKey: ["career", "roadmaps", id], queryFn: () => careerApi.roadmaps({ employee: id, page_size: 5 }), enabled: Boolean(id) });

  const person = personQ.data;
  const trendPoints = analyticsQ.data?.trend ?? [];
  const latest = trendPoints[trendPoints.length - 1];
  // v1 leads with plain goal progress; the T-score trend is kept for v2 (flag).
  const tscoreTrend = trendPoints.map((p, i) => ({ label: `#${i + 1}`, value: Number(p.t_score) }));
  const progressTrend = trendPoints.map((p, i) => ({ label: `#${i + 1}`, value: Math.round(Number(p.raw_score) * 100) }));
  const goals = goalsQ.data?.results ?? [];
  const overall = personProgress(goals);
  const overallStatus = overall.pct != null ? progressStatus(overall.pct) : null;
  const reviews = reviewsQ.data?.results ?? [];
  const roadmap = roadmapQ.data?.results?.[0];

  return (
    <div className="space-y-6">
      <div>
        <Link to="/org" className="mb-3 inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to people
        </Link>
        <PageHeader
          eyebrow="Talent"
          title={person?.display ?? "Employee profile"}
          description={person ? [person.title, ROLE_LABEL[person.role as Role]].filter(Boolean).join(" · ") : "Growth, performance and development in one place."}
        />
      </div>

      {/* Identity */}
      <Card className="p-5">
        {personQ.isLoading ? (
          <LinesSkeleton lines={2} />
        ) : personQ.isError ? (
          <ErrorState error={personQ.error} onRetry={() => personQ.refetch()} compact />
        ) : person ? (
          <div className="flex flex-wrap items-center gap-4">
            <Avatar className="h-14 w-14">
              <AvatarFallback className="text-base">{initials(person.display)}</AvatarFallback>
            </Avatar>
            <div className="min-w-0">
              <p className="text-lg font-bold text-foreground">{person.display}</p>
              <p className="text-sm text-muted-foreground">{person.title || ROLE_LABEL[person.role as Role]}</p>
            </div>
            <div className="ml-auto flex flex-wrap items-center gap-4 text-sm">
              {person.manager && (
                <span className="text-muted-foreground">Reports to <span className="font-medium text-foreground">{person.manager.display}</span></span>
              )}
              <span className="text-muted-foreground">{person.direct_reports} direct report{person.direct_reports === 1 ? "" : "s"}</span>
              {latest ? (
                <span className="inline-flex items-center gap-2">
                  {/* v1: the plain status is the performance signal; the T-score
                      number is hidden (V1_HIDE_TSCORE) — kept for v2. */}
                  <StatusBadge status={latest.risk_status} dot />
                  {!V1_HIDE_TSCORE && (
                    <span className="text-xs tabular-nums text-muted-foreground" title={T_SCORE_PLAIN}>
                      Score {Number(latest.t_score).toFixed(0)}/100
                    </span>
                  )}
                </span>
              ) : (
                <Badge variant="muted">Not yet scored</Badge>
              )}
            </div>
          </div>
        ) : (
          <EmptyState compact title="Not available" description="This person isn't in your scope." />
        )}
      </Card>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* Performance — v1 leads with plain goal progress; the T-score trend is
            kept for v2 behind V1_HIDE_TSCORE. */}
        <DashboardSection title="Performance" icon={TrendingUp}>
          {!V1_HIDE_TSCORE ? (
            analyticsQ.isLoading ? (
              <LinesSkeleton lines={4} />
            ) : analyticsQ.isError ? (
              <ErrorState error={analyticsQ.error} onRetry={() => analyticsQ.refetch()} compact />
            ) : tscoreTrend.length >= 2 ? (
              <div>
                <p className="mb-2 text-xs text-muted-foreground">T-score across scored cycles (50 = cohort average)</p>
                <TrendChart data={tscoreTrend} height={200} />
              </div>
            ) : latest ? (
              <div>
                <div className="flex items-center gap-2">
                  <StatusBadge status={latest.risk_status} dot />
                  <span className="text-sm font-semibold text-foreground">{performanceLabel(latest.risk_status)}</span>
                </div>
                <ScoreBar className="mt-3" value={Number(latest.t_score)} status={latest.risk_status} />
                <p className="mt-2 text-xs text-muted-foreground" title={T_SCORE_PLAIN}>
                  Score {Number(latest.t_score).toFixed(0)}/100 · 50 = team average.
                </p>
              </div>
            ) : (
              <EmptyState compact icon={TrendingUp} title="No scores yet" description="Performance scores appear once computed for a cycle." />
            )
          ) : goalsQ.isLoading || analyticsQ.isLoading ? (
            <LinesSkeleton lines={4} />
          ) : overall.pct != null ? (
            <div className="space-y-4">
              {/* The plain lead: overall goal progress % + colored bar + status. */}
              <div>
                <div className="flex items-baseline justify-between">
                  <span className="text-sm text-muted-foreground">Overall goal progress</span>
                  <span className={cn("text-2xl font-bold tabular-nums leading-none", overallStatus && PROGRESS_TEXT_CLASS[overallStatus])}>
                    {Math.round(overall.pct)}%
                  </span>
                </div>
                <ProgressBar className="mt-2" pct={overall.pct} status={overallStatus} />
                <p className="mt-2 text-xs text-muted-foreground">
                  {overall.onTrack} of {overall.total} goal{overall.total === 1 ? "" : "s"} on track this cycle
                </p>
              </div>
              {progressTrend.length >= 2 && (
                <div>
                  <p className="mb-2 text-xs text-muted-foreground">Progress across scored cycles</p>
                  <TrendChart data={progressTrend} seriesName="Progress %" height={170} />
                </div>
              )}
            </div>
          ) : latest ? (
            <div className="flex items-center gap-2">
              <StatusBadge status={latest.risk_status} dot />
              <span className="text-sm font-semibold text-foreground">{performanceLabel(latest.risk_status)}</span>
            </div>
          ) : (
            <EmptyState compact icon={TrendingUp} title="No progress yet" description="Goal progress appears once KPIs are recorded for a cycle." />
          )}
        </DashboardSection>

        {/* Career roadmap */}
        <DashboardSection title="Career roadmap" icon={GraduationCap} to="/career" toLabel="Open">
          {roadmapQ.isLoading ? (
            <LinesSkeleton lines={4} />
          ) : roadmapQ.isError ? (
            <ErrorState error={roadmapQ.error} onRetry={() => roadmapQ.refetch()} compact />
          ) : roadmap ? (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="muted">Advisory · {roadmap.source === "AI" ? "AI-enriched" : "deterministic"}</Badge>
                {roadmap.target_jd_title || roadmap.target_position_title ? (
                  <span className="text-sm text-muted-foreground">Toward <span className="font-medium text-foreground">{roadmap.target_jd_title ?? roadmap.target_position_title}</span></span>
                ) : null}
              </div>
              <ol className="space-y-2">
                {roadmap.tiers.slice(0, 5).map((t) => (
                  <li key={t.index} className="flex gap-2.5 text-sm">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-secondary text-2xs font-semibold">{t.index + 1}</span>
                    <div>
                      <p className="font-medium">{t.title}</p>
                      <p className="text-2xs text-muted-foreground">{t.detail}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          ) : (
            <EmptyState compact icon={GraduationCap} title="No roadmap yet" description="A development roadmap appears here once created." />
          )}
        </DashboardSection>
      </div>

      {/* Goals */}
      <DashboardSection title="Goals & KPIs" icon={Target} to="/goals">
        {goalsQ.isLoading ? (
          <LinesSkeleton lines={4} />
        ) : goalsQ.isError ? (
          <ErrorState error={goalsQ.error} onRetry={() => goalsQ.refetch()} compact />
        ) : goals.length > 0 ? (
          <ul className="space-y-4">
            {goals.map((g) => (
              <li key={g.id} className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{g.title}</span>
                  <StatusBadge status={g.status} />
                </div>
                <ul className="space-y-1.5">
                  {g.kpis.map((k) => (
                    <li key={k.id} className="flex items-center justify-between gap-3 rounded-md bg-secondary/40 px-2.5 py-1.5">
                      <span className="min-w-0 flex-1 text-xs"><span className="font-medium">{k.name}</span></span>
                      <AttainmentBar actual={k.latest_actual} target={k.target_value} direction={k.direction} className="max-w-[12rem]" />
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState compact icon={Target} title="No goals" description="This person's goals for the cycle appear here." />
        )}
      </DashboardSection>

      {/* Reviews */}
      <DashboardSection title="Reviews" icon={FileText} to="/reviews">
        {reviewsQ.isLoading ? (
          <LinesSkeleton lines={3} />
        ) : reviewsQ.isError ? (
          <ErrorState error={reviewsQ.error} onRetry={() => reviewsQ.refetch()} compact />
        ) : reviews.length > 0 ? (
          <ul className="divide-y divide-border">
            {reviews.map((r) => (
              <li key={r.id} className="py-3 first:pt-0 last:pb-0">
                <div className="flex items-center justify-between gap-2">
                  <Link to={`/reviews/${r.id}`} className="text-sm font-medium hover:underline">Performance review</Link>
                  <StatusBadge status={r.state} dot />
                </div>
                {r.state === "FINALIZED" && r.final_body ? (
                  <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{r.final_body}</p>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState compact icon={FileText} title="No reviews" description="This person's reviews appear here." />
        )}
      </DashboardSection>
    </div>
  );
}
