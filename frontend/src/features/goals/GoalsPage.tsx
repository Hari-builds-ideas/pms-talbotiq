import * as React from "react";
import { Check, Plus, RefreshCw, Target, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Field } from "@/components/Field";
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
import { useAuth } from "@/lib/auth/AuthContext";
import { useCycles } from "@/lib/hooks/useCycles";
import { useDirectory } from "@/lib/hooks/useDirectory";
import { KPI_DIRECTION, humanize } from "@/lib/enums";
import { formatScore } from "@/lib/format";
import { sumWeights, weightsSumTo100 } from "@/lib/weights";
import { mapApiError } from "@/lib/errors";
import { notifyError, notifySuccess } from "@/lib/toast";
import { activeWeightTotal, useCycleScores, useGoalMutations, useGoals } from "./useGoals";
import type { CycleScore, Goal } from "@/lib/types";

export function GoalsPage() {
  // Managers can't list cycles (HRBP+ only), so resolve the working cycle from
  // the active cycle when available, else from the scope's own goals.
  const { active, nameOf } = useCycles();
  const goalsAll = useGoals(undefined);
  const rows = goalsAll.data?.results ?? [];
  const cycle = active?.id ?? rows[0]?.cycle;

  const goals = goalsAll;
  const scores = useCycleScores(cycle);
  const m = useGoalMutations(cycle);
  const [createOpen, setCreateOpen] = React.useState(false);
  const scoreByEmp = new Map<string, CycleScore>((scores.data ?? []).map((s) => [s.employee, s]));
  const employees = Array.from(new Set(rows.map((g) => g.employee)));

  return (
    <div>
      <PageHeader
        title="Goals & KPIs"
        description="Weighted goals with KPI attainment. Weights must sum to exactly 100. Record actuals, recompute scores, and approve."
        actions={
          <div className="flex items-center gap-2">
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
              <RefreshCw className="h-4 w-4" /> Recompute scores
            </Button>
            <Button onClick={() => setCreateOpen(true)} disabled={!cycle}>
              <Plus className="h-4 w-4" /> New goal
            </Button>
          </div>
        }
      />

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
            const score = scoreByEmp.get(emp);
            return (
              <div key={emp} className="space-y-3">
                <div className="flex flex-wrap items-center gap-3">
                  <PersonName id={emp} withAvatar className="text-sm font-semibold" />
                  {score && <StatusBadge status={score.risk_status} dot />}
                  {score && <span className="text-2xs text-muted-foreground">T-score {formatScore(score.t_score)}</span>}
                  <Badge variant={Math.abs(total - 100) < 0.005 ? "success" : "warning"}>
                    Active goal weight: {total.toFixed(2)} / 100
                  </Badge>
                </div>
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
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
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="font-medium">{goal.title}</p>
            {goal.objective && <p className="text-2xs text-muted-foreground">{goal.objective}</p>}
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <Badge variant="muted">weight {goal.weight}</Badge>
            <StatusBadge status={goal.status} />
          </div>
        </div>

        <ul className="space-y-2">
          {goal.kpis.map((k) => (
            <KpiRow key={k.id} kpi={k} mutation={mutations.recordActual} canRecord={isOwn} />
          ))}
        </ul>

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
  return (
    <li className="flex items-center justify-between gap-2 rounded-md bg-secondary/40 px-2.5 py-1.5">
      <div className="min-w-0">
        <span className="text-sm font-medium">{kpi.name}</span>
        <span className="ml-2 text-2xs text-muted-foreground">
          weight {kpi.weight} · target {formatScore(kpi.target_value)} {kpi.unit} · {humanize(kpi.direction)}
        </span>
      </div>
      {/* Actuals are own-only (update_own_actuals) — managers don't record for reports. */}
      {canRecord && (
        <div className="flex shrink-0 items-center gap-1.5">
          <Input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="actual"
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
                .then(() => { setValue(""); notifySuccess("Actual recorded"); })
                .catch(notifyError)
            }
          >
            Record
          </Button>
        </div>
      )}
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

  React.useEffect(() => {
    if (open) {
      setEmployee(""); setTitle(""); setObjective(""); setWeight("100"); setKpis([newKpi()]); setError(null);
    }
  }, [open]);

  const kpiTotal = sumWeights(kpis);
  const kpiOk = weightsSumTo100(kpis);
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
            KPI weights must sum to exactly 100, and the employee's active goal weights must also sum to 100.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[60vh] space-y-4 overflow-y-auto scrollbar-thin pr-1">
          {error && <p className="rounded-md bg-danger-subtle px-3 py-2 text-sm text-danger">{error}</p>}
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

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">KPIs</span>
              <Badge variant={kpiOk ? "success" : "warning"}>KPI weight: {kpiTotal.toFixed(2)} / 100</Badge>
            </div>
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
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            onClick={submit}
            loading={mutation.isPending}
            disabled={!employee || !title.trim() || !kpiOk || kpis.some((k) => !k.name.trim())}
          >
            Create goal
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function patch(setKpis: React.Dispatch<React.SetStateAction<DraftKpi[]>>, i: number, p: Partial<DraftKpi>) {
  setKpis((prev) => prev.map((k, idx) => (idx === i ? { ...k, ...p } : k)));
}
