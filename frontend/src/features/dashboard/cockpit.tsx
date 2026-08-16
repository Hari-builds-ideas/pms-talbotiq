import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Activity,
  CreditCard,
  FileText,
  GraduationCap,
  Inbox,
  MessageSquareText,
  ShieldCheck,
  Target,
  Users,
} from "lucide-react";
import { Panel } from "@/components/Panel";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { StatusBadge } from "@/components/StatusBadge";
import { PersonName } from "@/components/PersonName";
import { LinesSkeleton } from "@/components/Skeletons";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { GiveFeedbackDialog } from "@/features/feedback/GiveFeedbackDialog";
import { notifyError, notifySuccess } from "@/lib/toast";
import {
  adminApi,
  auditApi,
  billingApi,
  careerApi,
  cyclesApi,
  feedbackApi,
  goalsApi,
  reviewsApi,
} from "@/lib/api/endpoints";
import { ROLE_LABEL, humanize, type Role } from "@/lib/enums";
import { formatDateTime, formatScore } from "@/lib/format";

const ACTIVE_REVIEW_STATES = ["DRAFT", "AI_DRAFTING", "PENDING_HUMAN_REVIEW", "EDITING", "APPROVED"];

// ── Manager: reviews awaiting my action ──────────────────────────────────────
export function ReviewsAwaitingTile() {
  const q = useQuery({
    queryKey: ["reviews", "list", { dashboard: true }],
    queryFn: () => reviewsApi.list({ page_size: 50 }),
  });
  const items = (q.data?.results ?? []).filter((r) => ACTIVE_REVIEW_STATES.includes(r.state));
  return (
    <Panel
      title="Reviews to act on"
      icon={FileText}
      to="/reviews"
      aside={items.length > 0 ? <Badge variant="warning">{items.length}</Badge> : undefined}
    >
      {q.isLoading ? (
        <LinesSkeleton lines={3} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} compact />
      ) : items.length > 0 ? (
        <ul className="divide-y divide-border">
          {items.slice(0, 6).map((r) => (
            <li key={r.id} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
              <Link to={`/reviews/${r.id}`} className="min-w-0 hover:underline">
                <PersonName id={r.employee} name={r.employee_name} className="text-sm font-medium" />
              </Link>
              <StatusBadge status={r.state} dot />
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState compact icon={FileText} title="No reviews waiting" description="Reviews you draft or approve appear here." />
      )}
    </Panel>
  );
}

// ── HRBP: feedback summaries to release ──────────────────────────────────────
export function FeedbackSummariesTile() {
  const q = useQuery({ queryKey: ["feedback", "summaries", "review"], queryFn: () => feedbackApi.summariesReview() });
  const items = q.data?.results ?? [];
  return (
    <Panel
      title="Summaries to release"
      icon={MessageSquareText}
      to="/feedback"
      aside={items.length > 0 ? <Badge variant="warning">{items.length}</Badge> : undefined}
    >
      {q.isLoading ? (
        <LinesSkeleton lines={3} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} compact />
      ) : items.length > 0 ? (
        <ul className="divide-y divide-border">
          {items.slice(0, 6).map((s) => (
            <li key={s.id} className="py-2.5 first:pt-0 last:pb-0">
              <Link
                to={`/feedback?tab=review&cycle=${s.cycle}`}
                className="tap-target flex items-center justify-between gap-3 hover:underline"
              >
                <span className="min-w-0 text-sm">
                  360 for <PersonName id={s.subject} name={s.subject_name} className="font-medium" />
                </span>
                <StatusBadge status={s.status} dot />
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState compact icon={MessageSquareText} title="Nothing to release" description="AI feedback summaries awaiting your review appear here." />
      )}
    </Panel>
  );
}

// ── Admin: tenant health (users by role) ─────────────────────────────────────
export function TenantHealthTile() {
  // Counts come from the DB-aggregated stats endpoint, not a full user-list
  // download — the tile stays O(1) regardless of tenant size.
  const q = useQuery({ queryKey: ["admin", "users", "stats"], queryFn: adminApi.userStats });
  const byRole = q.data?.active_by_role ?? {};
  const inactive = q.data?.inactive ?? 0;
  return (
    <Panel title="Tenant health" icon={Users} to="/admin/users">
      {q.isLoading ? (
        <LinesSkeleton lines={3} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} compact />
      ) : (
        <div className="space-y-2.5">
          {(["ADMIN", "HRBP", "MANAGER", "EMPLOYEE"] as Role[]).map((r) => (
            <div key={r} className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">{ROLE_LABEL[r]}</span>
              <span className="font-semibold tabular-nums">{byRole[r] ?? 0}</span>
            </div>
          ))}
          <div className="flex items-center justify-between border-t border-border pt-2 text-sm">
            <span className="text-muted-foreground">Inactive</span>
            <span className="font-semibold tabular-nums">{inactive}</span>
          </div>
        </div>
      )}
    </Panel>
  );
}

// ── Admin: entitlement summary ───────────────────────────────────────────────
export function EntitlementTile() {
  const q = useQuery({ queryKey: ["billing", "entitlement"], queryFn: billingApi.entitlement });
  const e = q.data;
  return (
    <Panel title="Plan & seats" icon={CreditCard} to="/admin/billing" toLabel="Manage">
      {q.isLoading ? (
        <LinesSkeleton lines={2} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} compact />
      ) : e ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Tier</span>
            <Badge variant={e.feature_packs.includes("FULL_AI") ? "success" : "secondary"}>{e.tier_label}</Badge>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Seats</span>
            <span className="font-semibold tabular-nums">{e.seat_count}</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {e.feature_packs.map((p) => (
              <Badge key={p} variant="outline">{p}</Badge>
            ))}
          </div>
        </div>
      ) : null}
    </Panel>
  );
}

// ── Admin/HRBP: recent audit activity ────────────────────────────────────────
export function RecentAuditTile() {
  const q = useQuery({ queryKey: ["audit", "logs", { dashboard: true }], queryFn: () => auditApi.logs({ page_size: 6 }) });
  const items = q.data?.results ?? [];
  return (
    <Panel title="Recent activity" icon={Activity} to="/audit">
      {q.isLoading ? (
        <LinesSkeleton lines={4} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} compact />
      ) : items.length > 0 ? (
        <ul className="space-y-2">
          {items.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-2 text-sm">
              <code className="truncate rounded bg-secondary px-1.5 py-0.5 font-mono text-2xs">{a.action}</code>
              <span className="shrink-0 text-2xs text-muted-foreground">{formatDateTime(a.created_at)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState compact icon={ShieldCheck} title="No activity yet" />
      )}
    </Panel>
  );
}

// ── Employee: my goals + progress (record own actuals) ───────────────────────
export function MyGoalsTile() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["goals", "mine"], queryFn: () => goalsApi.list({ page_size: 50 }) });
  const goals = q.data?.results ?? [];
  const record = useMutation({
    mutationFn: (v: { kpiId: string; value: string }) => goalsApi.recordActual(v.kpiId, v.value),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["goals", "mine"] });
      notifySuccess("Actual recorded", "Your manager can recompute scores to reflect it.");
    },
    onError: (e) => notifyError(e),
  });
  return (
    <Panel title="My goals & KPIs" icon={Target}>
      {q.isLoading ? (
        <LinesSkeleton lines={3} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} compact />
      ) : goals.length > 0 ? (
        <ul className="space-y-3">
          {goals.map((g) => (
            <li key={g.id} className="space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium">{g.title}</span>
                <StatusBadge status={g.status} />
              </div>
              <ul className="space-y-1">
                {g.kpis.map((k) => (
                  <MyKpiRow key={k.id} kpi={k} onRecord={(value) => record.mutate({ kpiId: k.id, value })} saving={record.isPending} />
                ))}
              </ul>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState compact icon={Target} title="No goals yet" description="Your goals for the active cycle will appear here." />
      )}
    </Panel>
  );
}

function MyKpiRow({
  kpi,
  onRecord,
  saving,
}: {
  kpi: { id: string; name: string; target_value: string; unit: string; latest_actual?: string | null };
  onRecord: (value: string) => void;
  saving: boolean;
}) {
  const [value, setValue] = React.useState("");
  return (
    <li className="flex items-center justify-between gap-2 rounded-md bg-secondary/40 px-2.5 py-1.5">
      <span className="min-w-0 text-xs">
        <span className="font-medium">{kpi.name}</span>
        <span className="ml-1.5 text-muted-foreground">
          {kpi.latest_actual != null ? `${formatScore(kpi.latest_actual)}/${formatScore(kpi.target_value)}` : `target ${formatScore(kpi.target_value)} ${kpi.unit}`}
        </span>
      </span>
      <span className="flex shrink-0 items-center gap-1">
        <Input value={value} onChange={(e) => setValue(e.target.value)} placeholder="actual" className="h-7 w-16 text-xs" inputMode="decimal" />
        <Button size="sm" variant="ghost" disabled={!value.trim()} loading={saving} onClick={() => { onRecord(value.trim()); setValue(""); }}>
          Log
        </Button>
      </span>
    </li>
  );
}

// ── Employee: my review status ───────────────────────────────────────────────
export function MyReviewTile() {
  const q = useQuery({ queryKey: ["reviews", "mine"], queryFn: () => reviewsApi.list({ page_size: 20 }) });
  const reviews = q.data?.results ?? [];
  return (
    <Panel title="My review" icon={FileText}>
      {q.isLoading ? (
        <LinesSkeleton lines={2} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} compact />
      ) : reviews.length > 0 ? (
        <ul className="space-y-2.5">
          {reviews.map((r) => (
            <li key={r.id} className="space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Current cycle</span>
                <StatusBadge status={r.state} dot />
              </div>
              {r.state === "FINALIZED" && r.final_body ? (
                <p className="line-clamp-3 text-sm text-foreground">{r.final_body}</p>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Your manager is working on this review. You'll see it here once finalized.
                </p>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState compact icon={FileText} title="No review yet" description="Your review for the active cycle will appear here." />
      )}
    </Panel>
  );
}

// ── Employee: feedback requests awaiting me ──────────────────────────────────
export function MyFeedbackRequestsTile() {
  const q = useQuery({ queryKey: ["feedback", "requests", "mine"], queryFn: feedbackApi.requestsMine });
  const pending = (q.data ?? []).filter((r) => r.status === "PENDING");
  const [give, setGive] = React.useState<{ cycleId: string; relationship: string } | null>(null);
  return (
    <Panel title="Feedback requests" icon={MessageSquareText} aside={pending.length > 0 ? <Badge variant="warning">{pending.length}</Badge> : undefined}>
      {q.isLoading ? (
        <LinesSkeleton lines={2} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} compact />
      ) : pending.length > 0 ? (
        <ul className="divide-y divide-border">
          {pending.map((r) => (
            <li key={r.id} className="flex items-center justify-between gap-2 py-2.5 first:pt-0 last:pb-0 text-sm">
              <span>{humanize(r.relationship)} feedback requested</span>
              <Button size="sm" onClick={() => setGive({ cycleId: r.cycle, relationship: r.relationship })}>Give</Button>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState compact icon={Inbox} title="No requests" description="360 feedback requests for you to complete appear here." />
      )}
      <GiveFeedbackDialog open={Boolean(give)} onOpenChange={(o) => !o && setGive(null)} cycleId={give?.cycleId ?? null} relationship={give?.relationship} />
    </Panel>
  );
}

// ── Employee: my career roadmap ──────────────────────────────────────────────
export function MyRoadmapTile() {
  const q = useQuery({ queryKey: ["career", "roadmap", "mine"], queryFn: careerApi.roadmap });
  const roadmap = q.data?.results?.[0];
  return (
    <Panel title="My career roadmap" icon={GraduationCap} to="/career" toLabel="Open">
      {q.isLoading ? (
        <LinesSkeleton lines={3} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} compact />
      ) : roadmap ? (
        <div className="space-y-2.5">
          <Badge variant="muted">Advisory · {roadmap.source === "AI" ? "AI-enriched" : "deterministic"}</Badge>
          <ol className="space-y-2">
            {roadmap.tiers.slice(0, 4).map((t) => (
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
        <EmptyState compact icon={GraduationCap} title="No roadmap yet" description="Your development roadmap will appear here." />
      )}
    </Panel>
  );
}

// ── small helper hooks for stat strips ───────────────────────────────────────
// Employees can't list cycles (HRBP+ only), so the cycle id is derived from the
// caller's own goals and passed in; scores/me is readable by the owner.
export function useMyScore(cycleId?: string) {
  return useQuery({
    queryKey: ["cycles", "myscore", cycleId],
    queryFn: () => cyclesApi.myScore(cycleId!),
    enabled: Boolean(cycleId),
  });
}
