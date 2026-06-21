import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { Filter, ShieldCheck, X } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { DataTable } from "@/components/DataTable";
import { TableSkeleton } from "@/components/Skeletons";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { PersonName } from "@/components/PersonName";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { auditApi, type AuditFilters } from "@/lib/api/endpoints";
import { useDirectory } from "@/lib/hooks/useDirectory";
import { formatDateTime, shortId } from "@/lib/format";
import { humanize } from "@/lib/enums";
import type { AuditLog } from "@/lib/types";

const PAGE = 50;
const TARGET_TYPES = ["review", "succession_plan", "job_description", "user", "entitlement", "approval_route"];

// A bare "YYYY-MM-DD" from a date input means the whole local day. Send the
// inclusive boundaries as tz-aware instants so "To = today" includes today's
// rows (a midnight cutoff would silently drop them).
function dayStartISO(d: string): string | undefined {
  return d ? new Date(`${d}T00:00:00`).toISOString() : undefined;
}
function dayEndISO(d: string): string | undefined {
  return d ? new Date(`${d}T23:59:59.999`).toISOString() : undefined;
}

export function AuditPage() {
  const { nodes } = useDirectory();
  const [page, setPage] = React.useState(1);
  const [actor, setActor] = React.useState("all");
  const [targetType, setTargetType] = React.useState("all");
  const [action, setAction] = React.useState("");
  const [dateFrom, setDateFrom] = React.useState("");
  const [dateTo, setDateTo] = React.useState("");

  const filters: AuditFilters = {
    page,
    page_size: PAGE,
    ...(actor !== "all" ? { actor } : {}),
    ...(targetType !== "all" ? { target_type: targetType } : {}),
    ...(action.trim() ? { action: action.trim() } : {}),
    ...(dateFrom ? { date_from: dayStartISO(dateFrom) } : {}),
    ...(dateTo ? { date_to: dayEndISO(dateTo) } : {}),
  };

  const q = useQuery({
    queryKey: ["audit", "logs", filters],
    queryFn: () => auditApi.logs(filters),
  });

  const hasFilters =
    actor !== "all" || targetType !== "all" || action.trim() !== "" || dateFrom !== "" || dateTo !== "";

  function clearFilters() {
    setActor("all");
    setTargetType("all");
    setAction("");
    setDateFrom("");
    setDateTo("");
    setPage(1);
  }

  const columns = React.useMemo<ColumnDef<AuditLog, unknown>[]>(
    () => [
      {
        accessorKey: "created_at",
        header: "Time",
        cell: ({ row }) => <span className="whitespace-nowrap text-muted-foreground">{formatDateTime(row.original.created_at)}</span>,
      },
      { accessorKey: "actor", header: "Actor", cell: ({ row }) => (row.original.actor ? <PersonName id={row.original.actor} name={row.original.actor_name} /> : <span className="text-muted-foreground">System</span>) },
      {
        accessorKey: "action",
        header: "Action",
        cell: ({ row }) => <code className="rounded bg-secondary px-1.5 py-0.5 font-mono text-2xs">{row.original.action}</code>,
      },
      {
        accessorKey: "target_type",
        header: "Target",
        cell: ({ row }) => (
          <span className="flex items-center gap-1.5">
            <Badge variant="outline">{humanize(row.original.target_type)}</Badge>
            <span className="font-mono text-2xs text-muted-foreground">{shortId(row.original.target_id)}</span>
          </span>
        ),
      },
      {
        accessorKey: "justification",
        header: "Justification",
        cell: ({ row }) => <span className="text-muted-foreground">{row.original.justification || "—"}</span>,
      },
    ],
    [],
  );

  return (
    <div>
      <PageHeader
        title="Audit Console"
        description="A read-only, immutable record of every action in the tenant. Filter and review — nothing here can be edited or deleted."
      />

      <Card className="mb-4 flex flex-wrap items-end gap-3 p-4">
        <div className="space-y-1.5">
          <label className="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">
            <Filter className="h-3 w-3" /> Actor
          </label>
          <Select value={actor} onValueChange={(v) => { setActor(v); setPage(1); }}>
            <SelectTrigger className="w-44" aria-label="Filter by actor"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All actors</SelectItem>
              {Object.values(nodes).map((n) => (
                <SelectItem key={n.id} value={n.id}>{n.display}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <label className="text-2xs font-semibold uppercase tracking-wide text-muted-foreground">Target type</label>
          <Select value={targetType} onValueChange={(v) => { setTargetType(v); setPage(1); }}>
            <SelectTrigger className="w-44" aria-label="Filter by target type"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All types</SelectItem>
              {TARGET_TYPES.map((t) => (
                <SelectItem key={t} value={t}>{humanize(t)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <label className="text-2xs font-semibold uppercase tracking-wide text-muted-foreground">Action contains</label>
          <Input aria-label="Filter by action text" value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }} placeholder="e.g. approved" className="w-48" />
        </div>
        <div className="space-y-1.5">
          <label className="text-2xs font-semibold uppercase tracking-wide text-muted-foreground">From</label>
          <Input
            type="date"
            aria-label="Filter from date"
            value={dateFrom}
            max={dateTo || undefined}
            onChange={(e) => { setDateFrom(e.target.value); setPage(1); }}
            className="w-40"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-2xs font-semibold uppercase tracking-wide text-muted-foreground">To</label>
          <Input
            type="date"
            aria-label="Filter to date"
            value={dateTo}
            min={dateFrom || undefined}
            onChange={(e) => { setDateTo(e.target.value); setPage(1); }}
            className="w-40"
          />
        </div>
        {hasFilters && (
          <Button variant="ghost" size="sm" onClick={clearFilters}>
            <X className="h-4 w-4" /> Clear
          </Button>
        )}
      </Card>

      {q.isLoading ? (
        <TableSkeleton rows={8} cols={5} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data && q.data.results.length > 0 ? (
        <DataTable
          columns={columns}
          data={q.data.results}
          getRowId={(l) => l.id}
          enableSorting={false}
          pagination={{ page, pageSize: PAGE, total: q.data.count, onPageChange: setPage }}
        />
      ) : (
        <EmptyState
          icon={ShieldCheck}
          title={hasFilters ? "No matching entries" : "No audit entries"}
          description={hasFilters ? "Try widening your filters." : "Actions across the tenant will appear here."}
          action={hasFilters ? <Button variant="outline" onClick={clearFilters}>Clear filters</Button> : undefined}
        />
      )}
    </div>
  );
}
