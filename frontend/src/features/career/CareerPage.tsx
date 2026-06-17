import * as React from "react";
import { GraduationCap, Plus, RefreshCw, Sparkles, Target, Users } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Field } from "@/components/Field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { LinesSkeleton } from "@/components/Skeletons";
import { StatusBadge } from "@/components/StatusBadge";
import { PersonName } from "@/components/PersonName";
import { SourceBadge, HitlBanner, ConfidenceBadge } from "@/components/Hitl";
import { useAuth } from "@/lib/auth/AuthContext";
import { jdApi, orgApi } from "@/lib/api/endpoints";
import { useQuery } from "@tanstack/react-query";
import { humanize } from "@/lib/enums";
import { formatDate } from "@/lib/format";
import { mapApiError } from "@/lib/errors";
import { notifyError, notifySuccess } from "@/lib/toast";
import type { DevelopmentRoadmap, RoadmapProgressStatus } from "@/lib/types";
import {
  useCareerMutations,
  useMyRoadmaps,
  useRoadmapProgress,
  useScopedRoadmaps,
  useSkillGap,
} from "./useCareer";

const PROGRESS_OPTS: RoadmapProgressStatus[] = ["NOT_STARTED", "IN_PROGRESS", "DONE"];

export function CareerPage() {
  return (
    <div>
      <PageHeader
        title="Career Development"
        description="Advisory development roadmaps toward a target role — grounded in performance data, never auto-promotion. AI enrichment is human-reviewed; you decide what to act on."
      />
      <Tabs defaultValue="mine">
        <TabsList>
          <TabsTrigger value="mine">My development</TabsTrigger>
          <TabsTrigger value="team">My team</TabsTrigger>
        </TabsList>
        <TabsContent value="mine"><MyDevelopmentTab /></TabsContent>
        <TabsContent value="team"><TeamTab /></TabsContent>
      </Tabs>
    </div>
  );
}

/** Resolve target JD / Position UUIDs to readable labels, and supply the
 * target picker its options. PUBLISHED JDs + open/filled positions are the
 * selectable targets. */
function useRoleTargets() {
  const jds = useQuery({
    queryKey: ["jd", "published", "targets"],
    queryFn: () => jdApi.list({ status: "PUBLISHED", page_size: 200 }),
  });
  const positions = useQuery({
    queryKey: ["org", "positions", "targets"],
    queryFn: () => orgApi.positions({ page_size: 200 }),
  });
  const jdLabel = React.useCallback(
    (id: string | null) => {
      const jd = jds.data?.results.find((j) => j.id === id);
      return jd ? `${jd.title} · ${humanize(jd.level)}` : null;
    },
    [jds.data],
  );
  const positionLabel = React.useCallback(
    (id: string | null) => positions.data?.results.find((p) => p.id === id)?.title ?? null,
    [positions.data],
  );
  return { jds, positions, jdLabel, positionLabel };
}

// ── My development ────────────────────────────────────────────────────────────
function MyDevelopmentTab() {
  const q = useMyRoadmaps();
  const targets = useRoleTargets();
  const [pickTarget, setPickTarget] = React.useState(false);
  const roadmaps = q.data?.results ?? [];

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setPickTarget(true)}>
          <Target className="h-4 w-4" /> {roadmaps.length ? "Change target role" : "Choose target role"}
        </Button>
      </div>
      {q.isLoading ? (
        <LinesSkeleton lines={4} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : roadmaps.length === 0 ? (
        <EmptyState
          icon={GraduationCap}
          title="No roadmap yet"
          description="Choose a target role to generate your advisory development roadmap from your current performance data."
          action={<Button onClick={() => setPickTarget(true)}><Target className="h-4 w-4" /> Choose target role</Button>}
        />
      ) : (
        roadmaps.map((r) => <RoadmapCard key={r.id} roadmap={r} targets={targets} canManage />)
      )}
      <TargetDialog open={pickTarget} onOpenChange={setPickTarget} targets={targets} />
    </div>
  );
}

// ── My team ───────────────────────────────────────────────────────────────────
function TeamTab() {
  const q = useScopedRoadmaps();
  const targets = useRoleTargets();
  const { me } = useAuth();
  const rows = (q.data?.results ?? []).filter((r) => r.employee !== me?.id);

  return (
    <div className="space-y-4">
      {q.isLoading ? (
        <LinesSkeleton lines={4} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No team roadmaps"
          description="Development roadmaps for people in your scope appear here. You can refresh or AI-enrich them."
        />
      ) : (
        rows.map((r) => <RoadmapCard key={r.id} roadmap={r} targets={targets} canManage showEmployee />)
      )}
    </div>
  );
}

// ── one roadmap ─────────────────────────────────────────────────────────────
function RoadmapCard({
  roadmap,
  targets,
  canManage,
  showEmployee,
}: {
  roadmap: DevelopmentRoadmap;
  targets: ReturnType<typeof useRoleTargets>;
  canManage?: boolean;
  showEmployee?: boolean;
}) {
  const { hasFeature } = useAuth();
  const { regenerate, enrich } = useCareerMutations();
  const gap = useSkillGap(roadmap.id);
  const isAiDraft = roadmap.source === "AI" && roadmap.status === "DRAFT";
  const targetLabel =
    targets.jdLabel(roadmap.target_jd) ?? targets.positionLabel(roadmap.target_position) ?? "Selected role";

  async function doEnrich() {
    try {
      const res = await enrich.mutateAsync(roadmap.id);
      if (res.generated) notifySuccess("AI roadmap drafted", "Review the AI-enriched draft below.");
      else notifyError(res.detail ?? "Enrichment was skipped.");
    } catch (err) {
      const e = mapApiError(err);
      if (e.code === "no_provider" || e.status === 503) {
        notifyError("AI enrichment isn't configured yet — the deterministic roadmap is unchanged.");
      } else {
        notifyError(err);
      }
    }
  }

  return (
    <Panel
      title={showEmployee ? "Development roadmap" : "Your development roadmap"}
      icon={GraduationCap}
      aside={
        <span className="flex items-center gap-1.5 text-2xs text-muted-foreground">
          {showEmployee && <>for <PersonName id={roadmap.employee} name={roadmap.employee_name} className="font-semibold text-foreground" /> ·</>}
          toward <span className="font-semibold text-foreground">{targetLabel}</span>
        </span>
      }
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <SourceBadge source={roadmap.source} />
          <StatusBadge status={roadmap.status} dot />
          <Badge variant="muted">Advisory</Badge>
          {roadmap.confidence_score && <ConfidenceBadge score={roadmap.confidence_score} />}
          <span className="ml-auto text-2xs text-muted-foreground">Generated {formatDate(roadmap.generated_at)}</span>
        </div>

        {isAiDraft && (
          <HitlBanner
            source={roadmap.source}
            confidence={roadmap.confidence_score}
            message="This is an AI-enriched draft alongside your deterministic roadmap. It's advisory — decide what to act on."
          />
        )}

        <SkillGapView roadmapId={roadmap.id} gapQuery={gap} fallback={roadmap.skill_gap} />

        <TiersList roadmap={roadmap} canManage={canManage} />

        {canManage && (
          <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
            <Button
              variant="outline"
              size="sm"
              loading={regenerate.isPending}
              onClick={() =>
                regenerate
                  .mutateAsync(roadmap.id)
                  .then(() => notifySuccess("Roadmap refreshed", "Recomputed from current performance data."))
                  .catch(notifyError)
              }
            >
              <RefreshCw className="h-4 w-4" /> Refresh (deterministic)
            </Button>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span tabIndex={hasFeature("career_roadmap") ? -1 : 0}>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={!hasFeature("career_roadmap")}
                      loading={enrich.isPending}
                      onClick={doEnrich}
                    >
                      <Sparkles className="h-4 w-4 text-ai" /> Enrich with AI
                    </Button>
                  </span>
                </TooltipTrigger>
                {!hasFeature("career_roadmap") && (
                  <TooltipContent>Career AI enrichment is a Full AI feature — upgrade to unlock.</TooltipContent>
                )}
              </Tooltip>
            </TooltipProvider>
          </div>
        )}
      </div>
    </Panel>
  );
}

function SkillGapView({
  roadmapId,
  gapQuery,
  fallback,
}: {
  roadmapId: string;
  gapQuery: ReturnType<typeof useSkillGap>;
  fallback: DevelopmentRoadmap["skill_gap"];
}) {
  void roadmapId;
  const gap = gapQuery.data ?? fallback;
  if (!gap) return null;
  const weak = gap.weak_categories ?? [];
  return (
    <div className="rounded-lg border border-border bg-muted/30 p-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">Performance band</span>
        <Badge variant="muted">{humanize(gap.current_performance_band ?? "UNKNOWN")}</Badge>
        <span className="text-muted-foreground">→ target</span>
        <Badge variant="muted">{humanize(gap.required_performance_band ?? "—")}</Badge>
        {typeof gap.performance_band_gap === "number" && (
          <Badge variant={gap.performance_band_gap === 0 ? "success" : "warning"}>
            {gap.performance_band_gap === 0 ? "At required band" : `${gap.performance_band_gap}-band gap`}
          </Badge>
        )}
      </div>
      {weak.length > 0 && (
        <div className="mt-2">
          <p className="text-2xs font-medium text-muted-foreground">Focus areas (at-risk goals)</p>
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {weak.map((w) => (
              <li key={w.goal_id}>
                <Badge variant="outline">{w.goal}</Badge>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function TiersList({ roadmap, canManage }: { roadmap: DevelopmentRoadmap; canManage?: boolean }) {
  const progress = useRoadmapProgress(roadmap.id);
  const { setProgress } = useCareerMutations();
  const statusByTier = React.useMemo(() => {
    const map = new Map<number, RoadmapProgressStatus>();
    (progress.data ?? []).forEach((p) => map.set(p.tier_index, p.status));
    return map;
  }, [progress.data]);

  if (!roadmap.tiers.length) {
    return <p className="text-sm text-muted-foreground">No tiers generated yet.</p>;
  }
  return (
    <ol className="space-y-3">
      {roadmap.tiers.map((t) => {
        const status = statusByTier.get(t.index) ?? "NOT_STARTED";
        return (
          <li key={t.index} className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-secondary text-2xs font-semibold">
              {t.index + 1}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-medium">{t.title}</p>
                {canManage ? (
                  <Select
                    value={status}
                    onValueChange={(v) =>
                      setProgress
                        .mutateAsync({ id: roadmap.id, tier_index: t.index, status: v as RoadmapProgressStatus })
                        .then(() => notifySuccess("Progress updated"))
                        .catch(notifyError)
                    }
                  >
                    <SelectTrigger className="h-7 w-36 text-2xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {PROGRESS_OPTS.map((o) => (
                        <SelectItem key={o} value={o}>{humanize(o)}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <StatusBadge status={status} />
                )}
              </div>
              <p className="text-2xs text-muted-foreground">{t.detail}</p>
              {t.basis && <p className="mt-0.5 text-2xs text-muted-foreground/70">Basis: {t.basis}</p>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

// ── target selection dialog ─────────────────────────────────────────────────
function TargetDialog({
  open,
  onOpenChange,
  targets,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  targets: ReturnType<typeof useRoleTargets>;
}) {
  const { selectTarget } = useCareerMutations();
  const [jd, setJd] = React.useState("");
  React.useEffect(() => {
    if (open) setJd("");
  }, [open]);
  const options = targets.jds.data?.results ?? [];

  async function submit() {
    try {
      await selectTarget.mutateAsync({ target_jd: jd });
      notifySuccess("Target selected", "Your deterministic roadmap has been generated.");
      onOpenChange(false);
    } catch (err) {
      notifyError(err);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Choose a target role</DialogTitle>
          <DialogDescription>
            Pick a published job description. We generate an advisory roadmap from your current performance data.
          </DialogDescription>
        </DialogHeader>
        <Field label="Target role (published JD)" required>
          {options.length === 0 ? (
            <p className="text-2xs text-muted-foreground">
              No published JDs yet. Publish a job description in the JD Library first.
            </p>
          ) : (
            <Select value={jd} onValueChange={setJd}>
              <SelectTrigger><SelectValue placeholder="Select a role…" /></SelectTrigger>
              <SelectContent>
                {options.map((j) => (
                  <SelectItem key={j.id} value={j.id}>{j.title} · {humanize(j.level)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </Field>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} loading={selectTarget.isPending} disabled={!jd}>
            <Plus className="h-4 w-4" /> Generate roadmap
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
