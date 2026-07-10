import * as React from "react";
import { Check, ChevronDown, Info, Plus, RefreshCw, Sparkles, Target, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Field } from "@/components/Field";
import { GoalUpdates } from "./GoalUpdates";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { CardGridSkeleton } from "@/components/Skeletons";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { PersonName } from "@/components/PersonName";
import { WeightBar } from "@/components/WeightBar";
import { AttainmentBar } from "@/components/AttainmentBar";
import { useAuth } from "@/lib/auth/AuthContext";
import { useCycles } from "@/lib/hooks/useCycles";
import { useDirectory } from "@/lib/hooks/useDirectory";
import { KPI_DIRECTION, humanize } from "@/lib/enums";
import { formatScore } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ProgressBar } from "@/components/ProgressBar";
import {
  goalProgress,
  personProgress,
  PROGRESS_STATUS_LABEL,
  PROGRESS_TEXT_CLASS,
} from "@/lib/goalProgress";
import { sumWeights, weightsSumTo100 } from "@/lib/weights";
import { mapApiError } from "@/lib/errors";
import { goalsApi } from "@/lib/api/endpoints";
import { notifyError, notifySuccess } from "@/lib/toast";
import { activeWeightTotal, useGoalMutations, useGoals } from "./useGoals";
import type { Goal } from "@/lib/types";

// Plain-language explanations (copy only — no behavior/data change).
const WEIGHT_HINT =
  "Weight is how much a goal or KPI counts toward the overall result. A person's active goal weights must total 100.";
const RECOMPUTE_HINT =
  "Rolls the latest recorded KPI progress into the performance analytics and reports.";

/** Small info affordance: an (i) icon with a one-line plain-language tooltip. */
function InfoHint({ label, text }: { label: string; text: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button type="button" aria-label={label} className="inline-flex text-muted-foreground hover:text-foreground">
          <Info className="h-3 w-3" />
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-[16rem] text-xs leading-relaxed">{text}</TooltipContent>
    </Tooltip>
  );
}

/** The person's active goal-weight state, as plain guidance (not a glitch). */
function WeightSummary({ total }: { total: number }) {
  const ok = Math.abs(total - 100) < 0.005;
  if (ok) return <Badge variant="success">Goal weights 100 / 100</Badge>;
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <Badge variant="warning">Goal weights {total.toFixed(0)} / 100</Badge>
      <span className="text-2xs text-warning">should total 100 — adjust this person's goal weights</span>
    </span>
  );
}

export function GoalsPage() {
  // Managers can't list cycles (HRBP+ only), so resolve the working cycle from
  // the active cycle when available, else from the scope's own goals.
  const { active, nameOf } = useCycles();
  // Goals is an everyday surface for ALL roles (employees see their own, read +
  // own-actuals); the management actions below (create / recompute) are Manager+
  // only — gated so an employee never sees a button the server would deny (D31).
  const { atLeast } = useAuth();
  const goalsAll = useGoals(undefined);
  const rows = goalsAll.data?.results ?? [];
  const cycle = active?.id ?? rows[0]?.cycle;

  const goals = goalsAll;
  const m = useGoalMutations(cycle);
  const [createOpen, setCreateOpen] = React.useState(false);
  const employees = Array.from(new Set(rows.map((g) => g.employee)));

  return (
    <div>
      <PageHeader
        eyebrow="Performance"
        title="Goals & OKRs"
        description="How each person is tracking against their goals this cycle."
        actions={
          atLeast("MANAGER") ? (
            <div className="flex items-center gap-2">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    onClick={() =>
                      m.recompute
                        .mutateAsync(cycle)
                        .then(() => notifySuccess("Scores recomputed"))
                        .catch(notifyError)
                    }
                    loading={m.recompute.isPending}
                    disabled={!cycle}
                  >
                    <RefreshCw className="h-4 w-4" /> Refresh analytics
                  </Button>
                </TooltipTrigger>
                <TooltipContent className="max-w-[18rem] text-xs leading-relaxed">{RECOMPUTE_HINT}</TooltipContent>
              </Tooltip>
              <Button onClick={() => setCreateOpen(true)} disabled={!cycle}>
                <Plus className="h-4 w-4" /> New goal
              </Button>
            </div>
          ) : undefined
        }
      />

      {/* Plain-language explainer — the bar shows how far along each goal is. */}
      <div className="mb-4 rounded-xl border border-border bg-secondary/40 px-4 py-3 text-sm text-muted-foreground">
        Each person has a few <span className="font-medium text-foreground">goals</span> this cycle. The bar
        shows <span className="font-medium text-foreground">how far along</span> each goal is —{" "}
        <span className="font-medium text-success">green</span> is on track,{" "}
        <span className="font-medium text-warning">amber</span> is behind,{" "}
        <span className="font-medium text-danger">red</span> needs attention. Open{" "}
        <span className="font-medium text-foreground">Show details</span> for targets and KPIs.
      </div>

      <div className="mb-4 flex items-center gap-2 text-xs text-muted-foreground">
        <span className="font-medium">Cycle:</span>
        <Badge variant="secondary">{cycle ? nameOf(cycle) : "—"}</Badge>
      </div>

      {goals.isLoading ? (
        <CardGridSkeleton count={3} />
      ) : goals.isError ? (
        <ErrorState error={goals.error} onRetry={() => goals.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState icon={Target} title="No goals in this cycle" description="Create a weighted goal with KPIs to start." action={<Button onClick={() => setCreateOpen(true)}>New goal</Button>} />
      ) : (
        <div className="space-y-6">
          {employees.map((emp) => {
            const empGoals = rows.filter((g) => g.employee === emp);
            const total = activeWeightTotal(rows, emp);
            const prog = personProgress(empGoals);
            const weightsOk = Math.abs(total - 100) < 0.005;
            return (
              <div key={emp} className="space-y-3">
                {/* PERSON — who the goals belong to + the one-line plain answer. */}
                <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-b border-border pb-2">
                  <PersonName id={emp} withAvatar className="text-sm font-semibold" />
                  {/* The headline: "3 of 4 goals on track — 68% overall". */}
                  {prog.started > 0 ? (
                    <p className="text-sm text-muted-foreground">
                      <span className="font-semibold text-foreground">{prog.onTrack} of {empGoals.length}</span>{" "}
                      goal{empGoals.length === 1 ? "" : "s"} on track
                      {prog.pct != null && (
                        <> — <span className="font-semibold text-foreground">{Math.round(prog.pct)}%</span> overall</>
                      )}
                    </p>
                  ) : (
                    <p className="text-sm text-muted-foreground">Not started yet this cycle</p>
                  )}
                </div>
                {/* Weight guidance stays available but only shouts when it's OFF (needs fixing). */}
                {!weightsOk && (
                  <span className="inline-flex flex-wrap items-center gap-1">
                    <WeightSummary total={total} />
                    <InfoHint label="What is weight?" text={WEIGHT_HINT} />
                  </span>
                )}
                {/* GOALS — belong to the person above (indented under them). */}
                <div className="grid grid-cols-1 gap-4 border-l-2 border-border/60 pl-3 lg:grid-cols-2 lg:pl-4">
                  {empGoals.map((g) => (
                    <GoalCard key={g.id} goal={g} mutations={m} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <NewGoalDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        cycle={cycle}
        cycleName={nameOf(cycle)}
        existingGoals={rows}
        mutation={m.create}
      />
    </div>
  );
}

function GoalCard({ goal, mutations }: { goal: Goal; mutations: ReturnType<typeof useGoalMutations> }) {
  const { atLeast, me } = useAuth();
  const isOwn = goal.employee === me?.id;
  const [open, setOpen] = React.useState(false);
  const prog = goalProgress(goal);

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        {/* HEADLINE — title + big % + colored bar + one-word status. The whole
            answer, no jargon, readable in a glance. */}
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="font-medium leading-tight">{goal.title}</p>
            {goal.objective && <p className="mt-0.5 text-2xs text-muted-foreground">{goal.objective}</p>}
          </div>
          <div className="shrink-0 text-right">
            {prog.pct == null ? (
              <span className="text-sm font-medium text-muted-foreground">Not started</span>
            ) : (
              <span className={cn("text-2xl font-bold tabular-nums leading-none", prog.status && PROGRESS_TEXT_CLASS[prog.status])}>
                {Math.round(prog.pct)}%
              </span>
            )}
          </div>
        </div>

        <ProgressBar pct={prog.pct} status={prog.status} />

        <div className="flex items-center justify-between">
          {prog.status ? (
            <span className={cn("text-sm font-semibold", PROGRESS_TEXT_CLASS[prog.status])}>
              {PROGRESS_STATUS_LABEL[prog.status]}
            </span>
          ) : (
            <span className="text-sm text-muted-foreground">No progress recorded yet</span>
          )}
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            className="inline-flex items-center gap-1 text-2xs font-medium text-muted-foreground hover:text-foreground"
          >
            {open ? "Hide details" : "Show details"}
            <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} />
          </button>
        </div>

        {/* DETAILS — everything technical, hidden until asked for. */}
        {open && (
          <div className="space-y-3 border-t border-border pt-3">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-muted-foreground">
              <StatusBadge status={goal.status} />
              <span>How much this counts: <span className="font-medium tabular-nums text-foreground">{goal.weight}</span></span>
            </div>

            {/* KPIs — the measurable targets that make up this goal. */}
            <div className="space-y-1.5">
              <p className="text-2xs font-semibold uppercase tracking-wide text-muted-foreground">KPIs</p>
              <ul className="space-y-2">
                {goal.kpis.map((k) => (
                  <KpiRow key={k.id} kpi={k} mutation={mutations.recordActual} canRecord={isOwn} />
                ))}
              </ul>
            </div>

            {/* Progress timeline (AGENT_UX_V3 Part 2.3) — the goal's recent updates. */}
            <GoalUpdates goalId={goal.id} canAdd={isOwn} />

            <div className="flex items-center justify-between border-t border-border pt-2">
              <span className="text-2xs text-muted-foreground">
                {goal.approved_by ? "Approved" : "Awaiting approval"}
              </span>
              {atLeast("MANAGER") && !goal.approved_by && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    mutations.approve
                      .mutateAsync(goal.id)
                      .then(() => notifySuccess("Goal approved"))
                      .catch(notifyError)
                  }
                  loading={mutations.approve.isPending}
                >
                  <Check className="h-4 w-4" /> Approve
                </Button>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function KpiRow({
  kpi,
  mutation,
  canRecord,
}: {
  kpi: Goal["kpis"][number];
  mutation: ReturnType<typeof useGoalMutations>["recordActual"];
  canRecord: boolean;
}) {
  const [value, setValue] = React.useState("");
  const notRecorded =
    kpi.latest_actual === null || kpi.latest_actual === undefined || kpi.latest_actual === "";
  return (
    <li className="rounded-md bg-secondary/40 px-2.5 py-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <span className="text-sm font-medium">{kpi.name}</span>
          {/* Plain-English KPI detail (only seen inside "Show details"). */}
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-2xs text-muted-foreground">
            <span>How much this counts <span className="tabular-nums text-foreground">{kpi.weight}</span></span>
            <span>Goal <span className="tabular-nums text-foreground">{formatScore(kpi.target_value)}</span> {kpi.unit}</span>
            <span>{kpi.direction === "DECREASING" ? "Lower is better ↓" : "Higher is better ↑"}</span>
            <span>
              Progress{" "}
              {notRecorded ? (
                <span className="italic">not recorded yet</span>
              ) : (
                <span className="tabular-nums text-foreground">{formatScore(kpi.latest_actual)}</span>
              )}
            </span>
          </div>
        </div>
        {/* Actuals are own-only (update_own_actuals) — managers don't record for reports. */}
        {canRecord && (
          <div className="flex shrink-0 items-center gap-1.5">
            <Input
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="progress"
              className="h-7 w-20 text-xs"
              inputMode="decimal"
            />
            <Button
              size="sm"
              variant="ghost"
              disabled={!value.trim()}
              loading={mutation.isPending}
              onClick={() =>
                mutation
                  .mutateAsync({ kpiId: kpi.id, value: value.trim() })
                  .then(() => { setValue(""); notifySuccess("Progress recorded"); })
                  .catch(notifyError)
              }
            >
              Record
            </Button>
          </div>
        )}
      </div>
      {/* Attainment: latest actual vs target, direction-aware (BUILD_5 5.2). */}
      <AttainmentBar actual={kpi.latest_actual} target={kpi.target_value} direction={kpi.direction} className="mt-2 max-w-xs" />
    </li>
  );
}

interface DraftKpi {
  name: string;
  weight: string;
  target_value: string;
  direction: string;
  unit: string;
}
const newKpi = (): DraftKpi => ({ name: "", weight: "", target_value: "100", direction: "INCREASING", unit: "" });

function NewGoalDialog({
  open,
  onOpenChange,
  cycle,
  cycleName,
  existingGoals,
  mutation,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  cycle: string;
  cycleName: string;
  existingGoals: Goal[];
  mutation: ReturnType<typeof useGoalMutations>["create"];
}) {
  const { nodes } = useDirectory();
  const people = Object.values(nodes);
  const [employee, setEmployee] = React.useState("");
  const [title, setTitle] = React.useState("");
  const [objective, setObjective] = React.useState("");
  const [weight, setWeight] = React.useState("100");
  const [kpis, setKpis] = React.useState<DraftKpi[]>([newKpi()]);
  const [error, setError] = React.useState<string | null>(null);
  const [step, setStep] = React.useState<1 | 2>(1);
  const [aiPrompt, setAiPrompt] = React.useState("");
  const [aiBusy, setAiBusy] = React.useState(false);

  React.useEffect(() => {
    if (open) {
      setEmployee(""); setTitle(""); setObjective(""); setWeight("100"); setKpis([newKpi()]); setError(null); setStep(1); setAiPrompt("");
    }
  }, [open]);

  // AI goal-writer (RW_BUILD_5): a one-line intent → an editable SMART draft. It
  // PREFILLS the form (title, objective, KPIs with evenly-split weights summing to
  // 100) — nothing is saved until the human submits the normal create.
  async function aiDraft() {
    const intent = aiPrompt.trim();
    if (!intent) return;
    setAiBusy(true);
    try {
      const { draft } = await goalsApi.aiDraft(intent);
      setTitle(draft.title);
      setObjective(draft.objective);
      const ks = draft.kpis ?? [];
      if (ks.length) {
        const n = ks.length;
        const base = Math.floor((100 / n) * 100) / 100;
        setKpis(
          ks.map((k, i) => ({
            name: k.name,
            weight: (i === n - 1 ? 100 - base * (n - 1) : base).toFixed(2),
            target_value: k.target_value || "100",
            direction: k.direction === "DECREASING" ? "DECREASING" : "INCREASING",
            unit: k.unit || "",
          })),
        );
      }
      notifySuccess("Draft ready — review and edit before creating");
    } catch (err) {
      notifyError(err);
    } finally {
      setAiBusy(false);
    }
  }

  const kpiTotal = sumWeights(kpis);
  const kpiOk = weightsSumTo100(kpis);
  const detailsOk = Boolean(employee) && Boolean(title.trim());
  const existingActive = employee
    ? activeWeightTotal(existingGoals, employee)
    : 0;

  async function submit() {
    setError(null);
    try {
      await mutation.mutateAsync({
        employee, cycle, title: title.trim(), objective: objective.trim(),
        weight: String(Number(weight).toFixed(2)),
        kpis: kpis.map((k) => ({
          name: k.name.trim(), weight: String(Number(k.weight).toFixed(2)),
          target_value: String(Number(k.target_value).toFixed(4)), direction: k.direction, unit: k.unit.trim(),
        })),
      });
      notifySuccess("Goal created");
      onOpenChange(false);
    } catch (err) {
      setError(mapApiError(err).message);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>New goal · {cycleName}</DialogTitle>
          <DialogDescription>
            {step === 1
              ? "Step 1 of 2 — who the goal is for and what success looks like."
              : "Step 2 of 2 — add KPIs; their weights must sum to exactly 100."}
          </DialogDescription>
        </DialogHeader>

        {/* Two-step wizard: details → KPIs & weights. */}
        <div className="flex items-center gap-2 text-2xs font-medium">
          <span className={step === 1 ? "text-foreground" : "text-muted-foreground"}>1 · Details</span>
          <span className="h-px flex-1 bg-border" />
          <span className={step === 2 ? "text-foreground" : "text-muted-foreground"}>2 · KPIs &amp; weights</span>
        </div>

        <div className="max-h-[60vh] space-y-4 overflow-y-auto scrollbar-thin pr-1">
          {error && <p className="rounded-md bg-danger-subtle px-3 py-2 text-sm text-danger">{error}</p>}
          {step === 1 && (
          <>
          <div className="rounded-md border border-dashed border-ai/40 bg-ai-subtle/30 p-3">
            <p className="mb-1.5 flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wide text-ai">
              <Sparkles className="h-3.5 w-3.5" /> Draft with AI
            </p>
            <div className="flex gap-2">
              <Input
                value={aiPrompt}
                onChange={(e) => setAiPrompt(e.target.value)}
                placeholder="e.g. improve our sales response time"
              />
              <Button type="button" variant="outline" onClick={aiDraft} loading={aiBusy} disabled={!aiPrompt.trim()}>
                Draft
              </Button>
            </div>
            <p className="mt-1 text-2xs text-muted-foreground">Fills the fields below — review and edit before creating.</p>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Employee" required>
              <Select value={employee} onValueChange={setEmployee}>
                <SelectTrigger><SelectValue placeholder="Select…" /></SelectTrigger>
                <SelectContent>
                  {people.map((p) => (
                    <SelectItem key={p.id} value={p.id}>{p.display}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field
              label="Goal weight"
              required
              hint={employee ? `Employee's ACTIVE goal weight is ${existingActive.toFixed(2)}/100 (new goals start as DRAFT; activate keeps the sum at 100).` : undefined}
            >
              <Input value={weight} onChange={(e) => setWeight(e.target.value)} inputMode="decimal" />
            </Field>
          </div>
          <Field label="Title" required>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Deliver platform reliability" />
          </Field>
          <Field label="Objective">
            <Input value={objective} onChange={(e) => setObjective(e.target.value)} placeholder="What success looks like" />
          </Field>
          </>
          )}

          {step === 2 && (
          <div className="space-y-3">
            <span className="text-sm font-medium">KPIs</span>
            <WeightBar total={kpiTotal} />
            <div className="space-y-2">
              {kpis.map((k, i) => (
                <div key={i} className="grid grid-cols-12 items-end gap-2 rounded-md border border-border p-2.5">
                  <Field label="Name" className="col-span-4"><Input value={k.name} onChange={(e) => patch(setKpis, i, { name: e.target.value })} className="h-8" /></Field>
                  <Field label="Weight" className="col-span-2"><Input value={k.weight} onChange={(e) => patch(setKpis, i, { weight: e.target.value })} className="h-8" inputMode="decimal" /></Field>
                  <Field label="Target" className="col-span-2"><Input value={k.target_value} onChange={(e) => patch(setKpis, i, { target_value: e.target.value })} className="h-8" inputMode="decimal" /></Field>
                  <Field label="Direction" className="col-span-3">
                    <Select value={k.direction} onValueChange={(v) => patch(setKpis, i, { direction: v })}>
                      <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {KPI_DIRECTION.map((d) => (
                          <SelectItem key={d} value={d}>{humanize(d)}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </Field>
                  <div className="col-span-1 flex justify-end pb-1">
                    {kpis.length > 1 && (
                      <Button variant="ghost" size="icon-sm" className="text-danger" onClick={() => setKpis((s) => s.filter((_, idx) => idx !== i))} aria-label="Remove KPI">
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                </div>
              ))}
              <Button variant="outline" size="sm" onClick={() => setKpis((s) => [...s, newKpi()])}>
                <Plus className="h-4 w-4" /> Add KPI
              </Button>
            </div>
          </div>
          )}
        </div>

        <DialogFooter>
          {step === 1 ? (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
              <Button onClick={() => setStep(2)} disabled={!detailsOk}>Next: KPIs</Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={() => setStep(1)}>Back</Button>
              <Button
                onClick={submit}
                loading={mutation.isPending}
                disabled={!detailsOk || !kpiOk || kpis.some((k) => !k.name.trim())}
              >
                Create goal
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function patch(setKpis: React.Dispatch<React.SetStateAction<DraftKpi[]>>, i: number, p: Partial<DraftKpi>) {
  setKpis((prev) => prev.map((k, idx) => (idx === i ? { ...k, ...p } : k)));
}
