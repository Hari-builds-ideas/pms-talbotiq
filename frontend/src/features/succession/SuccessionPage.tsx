import * as React from "react";
import { GitBranch, Grid3x3, Plus, ShieldAlert } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Field } from "@/components/Field";
import { Input } from "@/components/ui/input";
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
import { CardGridSkeleton, LinesSkeleton } from "@/components/Skeletons";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { NineBoxGrid } from "@/components/NineBoxGrid";
import { CoverageHeatmap } from "@/components/CoverageHeatmap";
import { RoleSheet } from "./RoleSheet";
import {
  useNineBox,
  useSuccessionDashboard,
  useSuccessionMutations,
} from "./useSuccession";
import { useAuth } from "@/lib/auth/AuthContext";
import { useDirectory } from "@/lib/hooks/useDirectory";
import { useCycles } from "@/lib/hooks/useCycles";
import { CRITICALITY, KNOWLEDGE_RISK, PERFORMANCE_BAND, humanize } from "@/lib/enums";
import { notifyError, notifySuccess } from "@/lib/toast";
import type { CriticalRoleSummary } from "@/lib/types";

export function SuccessionPage() {
  const { atLeast } = useAuth();
  const canManageRoles = atLeast("HRBP");
  const [selected, setSelected] = React.useState<CriticalRoleSummary | null>(null);
  const [createOpen, setCreateOpen] = React.useState(false);

  return (
    <div>
      <PageHeader
        title="Succession"
        description="Critical-role coverage, the talent grid and successor bench. Every plan is a draft until a human publishes it."
        actions={
          canManageRoles ? (
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4" /> Mark critical role
            </Button>
          ) : undefined
        }
      />

      <Tabs defaultValue="coverage">
        <TabsList>
          <TabsTrigger value="coverage">Coverage</TabsTrigger>
          <TabsTrigger value="ninebox">9-box grid</TabsTrigger>
        </TabsList>

        <TabsContent value="coverage">
          <CoverageTab onSelect={setSelected} />
        </TabsContent>
        <TabsContent value="ninebox">
          <NineBoxTab />
        </TabsContent>
      </Tabs>

      <RoleSheet role={selected} onOpenChange={(o) => !o && setSelected(null)} />
      <CreateRoleDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}

function CoverageTab({ onSelect }: { onSelect: (r: CriticalRoleSummary) => void }) {
  const dash = useSuccessionDashboard();
  const roles = dash.data?.critical_roles ?? [];

  if (dash.isLoading) return <CardGridSkeleton count={3} />;
  if (dash.isError) return <ErrorState error={dash.error} onRetry={() => dash.refetch()} />;
  if (roles.length === 0) {
    return (
      <EmptyState
        icon={GitBranch}
        title="No critical roles yet"
        description="Mark a role as critical to start tracking succession coverage."
      />
    );
  }

  return (
    <div className="space-y-4">
      <CoverageHeatmap roles={roles} />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {roles.map((r) => (
        <button key={r.id} type="button" onClick={() => onSelect(r)} className="text-left">
          <Card className="h-full transition-shadow hover:shadow-sm">
            <CardContent className="space-y-3 p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-semibold">{r.name}</p>
                  <p className="text-2xs text-muted-foreground">{humanize(r.criticality)} criticality</p>
                </div>
                <StatusBadge status={r.coverage_status} dot />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={r.knowledge_risk === "HIGH" ? "danger" : r.knowledge_risk === "MEDIUM" ? "warning" : "muted"}>
                  <ShieldAlert className="h-3 w-3" /> {humanize(r.knowledge_risk)} knowledge risk
                </Badge>
                {r.published_plan && <Badge variant="success">Plan published</Badge>}
              </div>
            </CardContent>
          </Card>
        </button>
      ))}
      </div>
    </div>
  );
}

function NineBoxTab() {
  const { atLeast } = useAuth();
  const { active } = useCycles();
  const nineBox = useNineBox(active?.id);
  const { setNineBoxOverride, clearNineBoxOverride } = useSuccessionMutations();
  const [assessOpen, setAssessOpen] = React.useState(false);
  // HRBP/Admin can drag a person to a new cell (a persisted human override);
  // managers/employees see the grid read-only (employees never reach succession).
  const canOverride = atLeast("HRBP");

  function reposition(placementId: string, box: number) {
    setNineBoxOverride
      .mutateAsync({ placementId, box })
      .then(() => notifySuccess("Placement overridden"))
      .catch(notifyError);
  }
  function clearOverride(placementId: string) {
    clearNineBoxOverride
      .mutateAsync(placementId)
      .then(() => notifySuccess("Reset to computed placement"))
      .catch(notifyError);
  }
  const pendingId =
    (setNineBoxOverride.isPending ? setNineBoxOverride.variables?.placementId ?? null : null) ??
    (clearNineBoxOverride.isPending ? clearNineBoxOverride.variables ?? null : null);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Performance (derived) × potential (human-assigned)
          {canOverride ? " · drag a card to override a placement" : ""}.{" "}
          {active ? `Cycle: ${active.name}` : ""}
        </p>
        {atLeast("MANAGER") && (
          <Button variant="outline" size="sm" onClick={() => setAssessOpen(true)}>
            <Grid3x3 className="h-4 w-4" /> Assess placement
          </Button>
        )}
      </div>
      <Panel title="Talent grid" icon={Grid3x3}>
        {nineBox.isLoading ? (
          <LinesSkeleton lines={6} />
        ) : nineBox.isError ? (
          <ErrorState error={nineBox.error} onRetry={() => nineBox.refetch()} compact />
        ) : nineBox.data && nineBox.data.results.length > 0 ? (
          <NineBoxGrid
            placements={nineBox.data.results}
            canOverride={canOverride}
            onReposition={reposition}
            onClearOverride={clearOverride}
            pendingId={pendingId}
          />
        ) : (
          <EmptyState compact icon={Grid3x3} title="No placements" description="Assess employees to populate the talent grid." />
        )}
      </Panel>
      <AssessDialog open={assessOpen} onOpenChange={setAssessOpen} cycle={active?.id} />
    </div>
  );
}

function AssessDialog({
  open,
  onOpenChange,
  cycle,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  cycle?: string;
}) {
  const { nodes } = useDirectory();
  const people = Object.values(nodes);
  const { assessNineBox } = useSuccessionMutations();
  const [employee, setEmployee] = React.useState("");
  const [band, setBand] = React.useState("MEDIUM");

  React.useEffect(() => {
    if (open) { setEmployee(""); setBand("MEDIUM"); }
  }, [open]);

  async function submit() {
    if (!cycle) return;
    try {
      await assessNineBox.mutateAsync({ employee, cycle, potential_band: band });
      notifySuccess("Placement assessed");
      onOpenChange(false);
    } catch (err) {
      notifyError(err);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Assess 9-box placement</DialogTitle>
          <DialogDescription>Performance is derived from scores; you set potential.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
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
          <Field label="Potential band" required>
            <Select value={band} onValueChange={setBand}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {PERFORMANCE_BAND.map((b) => (
                  <SelectItem key={b} value={b}>{humanize(b)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} loading={assessNineBox.isPending} disabled={!employee || !cycle}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CreateRoleDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const { nodes } = useDirectory();
  const people = Object.values(nodes);
  const { createRole } = useSuccessionMutations();
  const [name, setName] = React.useState("");
  const [incumbent, setIncumbent] = React.useState("none");
  const [criticality, setCriticality] = React.useState("HIGH");
  const [knowledgeRisk, setKnowledgeRisk] = React.useState("MEDIUM");

  React.useEffect(() => {
    if (open) { setName(""); setIncumbent("none"); setCriticality("HIGH"); setKnowledgeRisk("MEDIUM"); }
  }, [open]);

  async function submit() {
    try {
      await createRole.mutateAsync({
        name: name.trim(),
        incumbent: incumbent === "none" ? null : incumbent,
        criticality: criticality as "HIGH" | "CRITICAL",
        knowledge_risk: knowledgeRisk as "LOW" | "MEDIUM" | "HIGH",
      });
      notifySuccess("Critical role marked");
      onOpenChange(false);
    } catch (err) {
      notifyError(err);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Mark a critical role</DialogTitle>
          <DialogDescription>Track succession coverage for a key role.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <Field label="Role name" required>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Head of Platform" />
          </Field>
          <Field label="Incumbent">
            <Select value={incumbent} onValueChange={setIncumbent}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Vacant</SelectItem>
                {people.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.display}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Criticality">
              <Select value={criticality} onValueChange={setCriticality}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {CRITICALITY.map((c) => (
                    <SelectItem key={c} value={c}>{humanize(c)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Knowledge risk">
              <Select value={knowledgeRisk} onValueChange={setKnowledgeRisk}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {KNOWLEDGE_RISK.map((k) => (
                    <SelectItem key={k} value={k}>{humanize(k)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} loading={createRole.isPending} disabled={!name.trim()}>Mark role</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
