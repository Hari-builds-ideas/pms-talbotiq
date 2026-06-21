import * as React from "react";
import { BarChart3, Grid3x3, Lock, TrendingUp, Users } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { StatCard } from "@/components/StatCard";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { LinesSkeleton } from "@/components/Skeletons";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { PersonName } from "@/components/PersonName";
import { NineBoxGrid } from "@/components/NineBoxGrid";
import { useCalibration, useDepartment, useIndividual } from "./useAnalytics";
import { useAuth } from "@/lib/auth/AuthContext";
import { useDirectory } from "@/lib/hooks/useDirectory";
import { useCycles } from "@/lib/hooks/useCycles";
import { formatScore } from "@/lib/format";
import { TrendChart } from "@/components/TrendChart";

export function AnalyticsPage() {
  const { atLeast } = useAuth();
  return (
    <div>
      <PageHeader
        title="Analytics"
        description="Performance trends, department cohorts and the calibration grid. Small cohorts are aggregated for privacy."
      />
      <Tabs defaultValue="individual">
        <TabsList>
          <TabsTrigger value="individual">Individual</TabsTrigger>
          <TabsTrigger value="department">Department</TabsTrigger>
          {atLeast("HRBP") && <TabsTrigger value="calibration">Calibration</TabsTrigger>}
        </TabsList>
        <TabsContent value="individual"><IndividualTab /></TabsContent>
        <TabsContent value="department"><DepartmentTab /></TabsContent>
        {atLeast("HRBP") && (
          <TabsContent value="calibration"><CalibrationTab /></TabsContent>
        )}
      </Tabs>
    </div>
  );
}

function IndividualTab() {
  const { nameOf, nodes } = useDirectory();
  const { nameOf: cycleName } = useCycles();
  const [employee, setEmployee] = React.useState<string>("self");
  const q = useIndividual(employee === "self" ? undefined : employee);
  const trend = q.data?.trend ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-muted-foreground">Employee</span>
        <Select value={employee} onValueChange={setEmployee}>
          <SelectTrigger className="w-56" aria-label="Select employee"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="self">Myself</SelectItem>
            {Object.values(nodes).map((n) => (
              <SelectItem key={n.id} value={n.id}>{n.display}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Panel title="Performance trend" icon={TrendingUp}>
        {q.isLoading ? (
          <LinesSkeleton lines={4} />
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} compact />
        ) : trend.length > 0 ? (
          <div className="space-y-5">
            {/* Real per-cycle T-score trend (recharts). */}
            <TrendChart
              data={trend.map((pt) => ({ label: cycleName(pt.cycle), value: Number(pt.t_score) }))}
            />
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Cycle</TableHead>
                  <TableHead>T-score</TableHead>
                  <TableHead>Raw</TableHead>
                  <TableHead>Risk</TableHead>
                  <TableHead>Pace</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {trend.map((pt) => (
                  <TableRow key={pt.cycle}>
                    <TableCell>{cycleName(pt.cycle)}</TableCell>
                    <TableCell className="tabular-nums">{formatScore(pt.t_score)}</TableCell>
                    <TableCell className="tabular-nums">{pt.raw_score}</TableCell>
                    <TableCell><StatusBadge status={pt.risk_status} /></TableCell>
                    <TableCell>
                      {pt.pace_behind ? <Badge variant="warning">Behind</Badge> : <Badge variant="muted">On pace</Badge>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : (
          <EmptyState compact icon={TrendingUp} title="No trend yet" description={`No scored cycles for ${employee === "self" ? "you" : nameOf(employee)}.`} />
        )}
      </Panel>
    </div>
  );
}

function DepartmentTab() {
  const { nodes } = useDirectory();
  const { cycles, active, nameOf: cycleName } = useCycles();
  const [head, setHead] = React.useState<string>("");
  const [cycle, setCycle] = React.useState<string>("");

  React.useEffect(() => {
    if (active && !cycle) setCycle(active.id);
  }, [active, cycle]);

  const effectiveHead = head || Object.values(nodes)[0]?.id;
  const q = useDepartment(effectiveHead, cycle);
  const d = q.data;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground">Head</span>
          <Select value={head || effectiveHead || ""} onValueChange={setHead}>
            <SelectTrigger className="w-52" aria-label="Select head of org"><SelectValue placeholder="Select…" /></SelectTrigger>
            <SelectContent>
              {Object.values(nodes).map((n) => (
                <SelectItem key={n.id} value={n.id}>{n.display}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground">Cycle</span>
          <Select value={cycle} onValueChange={setCycle}>
            <SelectTrigger className="w-44" aria-label="Select cycle"><SelectValue placeholder="Select…" /></SelectTrigger>
            <SelectContent>
              {cycles.map((c) => (
                <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {q.isLoading ? (
        <LinesSkeleton lines={5} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : d ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Headcount" value={d.aggregate.headcount} icon={Users} />
            <StatCard label="Scored" value={d.aggregate.scored} icon={BarChart3} />
            <StatCard label="Mean T-score" value={formatScore(d.aggregate.mean_t_score)} tone="info" />
            <StatCard label="Median T-score" value={formatScore(d.aggregate.median_t_score)} tone="info" />
          </div>

          <Panel title="Risk distribution" icon={BarChart3}>
            <div className="flex flex-wrap gap-4">
              {(["ON_TRACK", "AT_RISK", "CRITICAL"] as const).map((r) => (
                <div key={r} className="flex items-center gap-2">
                  <StatusBadge status={r} />
                  <span className="text-lg font-semibold tabular-nums">{d.aggregate.risk_distribution[r] ?? 0}</span>
                </div>
              ))}
            </div>
          </Panel>

          {d.suppressed ? (
            <Alert variant="warning">
              <Lock />
              <AlertTitle>Cohort too small (&lt;{d.min_cohort})</AlertTitle>
              <AlertDescription>
                {d.note ?? "Individual values are suppressed for privacy."} This cohort has{" "}
                {d.cohort_size} member{d.cohort_size === 1 ? "" : "s"}; only the aggregate is shown.
              </AlertDescription>
            </Alert>
          ) : (
            <Panel title="Individuals" icon={Users}>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Employee</TableHead>
                    <TableHead>T-score</TableHead>
                    <TableHead>Risk</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {d.individuals.map((ind) => (
                    <TableRow key={ind.employee}>
                      <TableCell><PersonName id={ind.employee} withAvatar /></TableCell>
                      <TableCell className="tabular-nums">{formatScore(ind.t_score)}</TableCell>
                      <TableCell><StatusBadge status={ind.risk_status} /></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Panel>
          )}
          <p className="text-2xs text-muted-foreground">Cycle: {cycleName(cycle)}</p>
        </div>
      ) : null}
    </div>
  );
}

function CalibrationTab() {
  const { cycles, active } = useCycles();
  const [cycle, setCycle] = React.useState<string>("");
  React.useEffect(() => {
    if (active && !cycle) setCycle(active.id);
  }, [active, cycle]);

  const q = useCalibration(cycle);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-muted-foreground">Cycle</span>
        <Select value={cycle} onValueChange={setCycle}>
          <SelectTrigger className="w-44" aria-label="Select cycle"><SelectValue placeholder="Select…" /></SelectTrigger>
          <SelectContent>
            {cycles.map((c) => (
              <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Panel
        title="Calibration grid"
        icon={Grid3x3}
        aside={q.data ? <Badge variant="secondary">{q.data.total} placed</Badge> : undefined}
      >
        {q.isLoading ? (
          <LinesSkeleton lines={6} />
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} compact />
        ) : q.data && q.data.placements.length > 0 ? (
          <NineBoxGrid placements={q.data.placements} />
        ) : (
          <EmptyState compact icon={Grid3x3} title="No placements" description="No 9-box placements for this cycle." />
        )}
      </Panel>
    </div>
  );
}
