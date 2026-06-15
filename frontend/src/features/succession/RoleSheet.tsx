import * as React from "react";
import { Plus, Sparkles, UserPlus } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/Field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { LinesSkeleton } from "@/components/Skeletons";
import { StatusBadge } from "@/components/StatusBadge";
import { PersonName } from "@/components/PersonName";
import { HitlBanner, SourceBadge } from "@/components/Hitl";
import { useBench, usePlan, useSuccessionMutations } from "./useSuccession";
import { useAuth } from "@/lib/auth/AuthContext";
import { useDirectory } from "@/lib/hooks/useDirectory";
import { READINESS, humanize, type Readiness } from "@/lib/enums";
import { notifyError, notifySuccess } from "@/lib/toast";
import { mapApiError } from "@/lib/errors";
import type { CriticalRoleSummary } from "@/lib/types";

export function RoleSheet({
  role,
  onOpenChange,
}: {
  role: CriticalRoleSummary | null;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Sheet open={Boolean(role)} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-lg">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            {role?.name}
            {role && <StatusBadge status={role.coverage_status} dot />}
          </SheetTitle>
          <SheetDescription>
            {role && `${humanize(role.criticality)} criticality · ${humanize(role.knowledge_risk)} knowledge risk`}
          </SheetDescription>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto scrollbar-thin p-5">
          {role && <RoleBody role={role} />}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function RoleBody({ role }: { role: CriticalRoleSummary }) {
  const { atLeast } = useAuth();
  const canHrbp = atLeast("HRBP");
  const m = useSuccessionMutations();
  const bench = useBench(role.id);
  const [planId, setPlanId] = React.useState<string | null>(role.published_plan);

  React.useEffect(() => {
    setPlanId(role.published_plan);
  }, [role.id, role.published_plan]);

  async function generate() {
    try {
      const plan = await m.generate.mutateAsync(role.id);
      setPlanId(plan.id);
      notifySuccess("Analysis generated", "Review the draft plan and publish when ready.");
    } catch (err) {
      notifyError(err);
    }
  }

  return (
    <div className="space-y-6">
      {/* Bench */}
      <section className="space-y-2">
        <h4 className="text-sm font-semibold">Successor bench</h4>
        {bench.isLoading ? (
          <LinesSkeleton lines={3} />
        ) : bench.data && bench.data.results.length > 0 ? (
          <ul className="space-y-2">
            {bench.data.results.map((b) => (
              <li key={b.id} className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2">
                <div className="min-w-0">
                  <PersonName id={b.candidate} className="text-sm font-medium" />
                  {b.notes && <p className="truncate text-2xs text-muted-foreground">{b.notes}</p>}
                </div>
                <div className="flex items-center gap-1.5">
                  {b.readiness_overridden && <Badge variant="muted">Override</Badge>}
                  {atLeast("MANAGER") ? (
                    <Select
                      value={b.readiness}
                      onValueChange={(v) =>
                        m.setReadiness
                          .mutateAsync({ benchId: b.id, readiness: v as Readiness })
                          .then(() => notifySuccess("Readiness updated"))
                          .catch(notifyError)
                      }
                    >
                      <SelectTrigger className="h-7 w-36 text-xs"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {READINESS.map((r) => (
                          <SelectItem key={r} value={r}>{humanize(r)}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <StatusBadge status={b.readiness} />
                  )}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">No bench candidates yet.</p>
        )}
        {atLeast("MANAGER") && <AddBench roleId={role.id} mutation={m.addBench} />}
      </section>

      {/* Plan */}
      <section className="space-y-3 border-t border-border pt-5">
        <h4 className="text-sm font-semibold">Succession plan</h4>
        {planId ? (
          <PlanReview planId={planId} canHrbp={canHrbp} mutations={m} />
        ) : canHrbp ? (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              No plan yet. Generate a deterministic analysis to review and publish.
            </p>
            <Button onClick={generate} loading={m.generate.isPending}>
              <Sparkles className="h-4 w-4" /> Generate analysis
            </Button>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No published plan. Generating requires HRBP+.</p>
        )}
      </section>

      {canHrbp && (
        <section className="border-t border-border pt-4">
          <Button
            variant="ghost"
            size="sm"
            className="text-danger"
            onClick={() =>
              m.archiveRole.mutateAsync(role.id).then(() => notifySuccess("Role archived")).catch(notifyError)
            }
          >
            Archive role
          </Button>
        </section>
      )}
    </div>
  );
}

function AddBench({
  roleId,
  mutation,
}: {
  roleId: string;
  mutation: ReturnType<typeof useSuccessionMutations>["addBench"];
}) {
  const { nodes } = useDirectory();
  const [candidate, setCandidate] = React.useState("");

  return (
    <div className="flex items-end gap-2 pt-1">
      <Field label="Add candidate" className="flex-1">
        <Select value={candidate} onValueChange={setCandidate}>
          <SelectTrigger><SelectValue placeholder="Select a person…" /></SelectTrigger>
          <SelectContent>
            {Object.values(nodes).map((p) => (
              <SelectItem key={p.id} value={p.id}>{p.display}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <Button
        variant="outline"
        disabled={!candidate}
        loading={mutation.isPending}
        onClick={() =>
          mutation
            .mutateAsync({ roleId, candidate })
            .then(() => { setCandidate(""); notifySuccess("Bench candidate added"); })
            .catch(notifyError)
        }
      >
        <UserPlus className="h-4 w-4" /> Add
      </Button>
    </div>
  );
}

function PlanReview({
  planId,
  canHrbp,
  mutations,
}: {
  planId: string;
  canHrbp: boolean;
  mutations: ReturnType<typeof useSuccessionMutations>;
}) {
  const plan = usePlan(planId);
  const [actionText, setActionText] = React.useState("");
  const [enrichUnavailable, setEnrichUnavailable] = React.useState(false);
  const p = plan.data;

  if (plan.isLoading) return <LinesSkeleton lines={4} />;
  if (!p) return <p className="text-sm text-muted-foreground">Plan unavailable.</p>;

  const isPending = p.status === "PENDING_HUMAN_REVIEW";

  async function enrich() {
    setEnrichUnavailable(false);
    try {
      await mutations.enrich.mutateAsync(planId);
    } catch (err) {
      if (mapApiError(err).kind === "ai_unavailable") setEnrichUnavailable(true);
      else notifyError(err);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={p.status} dot />
        <StatusBadge status={p.coverage_status} />
        <SourceBadge source={p.source} />
      </div>

      {isPending && <HitlBanner source={p.source} confidence={p.confidence_score} message="This succession plan is a draft. Review the bench and action items, then publish — it only appears on the dashboard once a human publishes it." />}

      {p.red_flags.length > 0 && (
        <Alert variant="danger">
          <AlertTitle>Red flags</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-4">
              {p.red_flags.map((f, i) => (
                <li key={i}>{typeof f === "string" ? humanize(f) : f.detail ?? f.code}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      {p.ranked_bench.length > 0 && (
        <div>
          <p className="mb-1.5 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">Ranked bench</p>
          <ol className="space-y-1">
            {p.ranked_bench.map((b, i) => (
              <li key={`${b.candidate}-${i}`} className="flex items-center justify-between text-sm">
                <span><span className="text-muted-foreground">{i + 1}.</span> <PersonName id={b.candidate} /></span>
                <StatusBadge status={b.readiness} />
              </li>
            ))}
          </ol>
        </div>
      )}

      <div>
        <p className="mb-1.5 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">Action items</p>
        {p.action_items.length > 0 ? (
          <ul className="space-y-1">
            {p.action_items.map((a, i) => (
              <li key={i} className="rounded-md bg-secondary/50 px-3 py-1.5 text-sm">{a.text}</li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">No action items.</p>
        )}
        {canHrbp && isPending && (
          <div className="mt-2 flex items-end gap-2">
            <Field label="" className="flex-1">
              <Input value={actionText} onChange={(e) => setActionText(e.target.value)} placeholder="Add an action item…" />
            </Field>
            <Button
              variant="outline"
              disabled={!actionText.trim()}
              loading={mutations.addActionItem.isPending}
              onClick={() =>
                mutations.addActionItem
                  .mutateAsync({ id: planId, text: actionText.trim() })
                  .then(() => { setActionText(""); notifySuccess("Action item added"); })
                  .catch(notifyError)
              }
            >
              <Plus className="h-4 w-4" /> Add
            </Button>
          </div>
        )}
      </div>

      {enrichUnavailable && (
        <Alert variant="ai">
          <Sparkles />
          <AlertTitle>AI enrichment not available</AlertTitle>
          <AlertDescription>The Succession Analyzer isn't configured yet. The deterministic plan is unchanged.</AlertDescription>
        </Alert>
      )}

      {canHrbp && (
        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border pt-3">
          <Button variant="outline" onClick={enrich} loading={mutations.enrich.isPending}>
            <Sparkles className="h-4 w-4 text-ai" /> Enrich (Agent 4)
          </Button>
          <Button
            disabled={!isPending}
            loading={mutations.publish.isPending}
            onClick={() =>
              mutations.publish
                .mutateAsync(planId)
                .then(() => notifySuccess("Plan published", "It now appears on the dashboard."))
                .catch((err) => { notifyError(err); void plan.refetch(); })
            }
          >
            Publish plan
          </Button>
        </div>
      )}
    </div>
  );
}
