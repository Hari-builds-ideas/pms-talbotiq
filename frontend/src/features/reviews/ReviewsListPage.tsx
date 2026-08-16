import * as React from "react";
import { useNavigate } from "react-router-dom";
import type { ColumnDef } from "@tanstack/react-table";
import { FileText, Plus } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { DataTable } from "@/components/DataTable";
import { TableSkeleton } from "@/components/Skeletons";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { SetupNeeded } from "@/components/SetupNeeded";
import { CycleSetupDialog } from "@/features/cycles/CycleSetupDialog";
import { StatusBadge } from "@/components/StatusBadge";
import { PersonName } from "@/components/PersonName";
import { SourceBadge } from "@/components/Hitl";
import { Button } from "@/components/ui/button";
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
import { Field } from "@/components/Field";
import { useReviews } from "./useReviews";
import { useCycles } from "@/lib/hooks/useCycles";
import { useScopedPeople } from "@/lib/hooks/useScopedPeople";
import { useAuth } from "@/lib/auth/AuthContext";
import { reviewsApi } from "@/lib/api/endpoints";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { notifyError, notifySuccess } from "@/lib/toast";
import { mapApiError } from "@/lib/errors";
import type { Review } from "@/lib/types";

const PAGE_SIZE = 50;

export function ReviewsListPage() {
  const navigate = useNavigate();
  // Reviews is an everyday surface for ALL roles — the list is own-scoped server-side
  // (VIEW_OWN_REVIEW), so an employee sees their own review(s). Creating a review is
  // Manager+ (MANAGE_REVIEWS) — gate the "New review" entry points (D31).
  const { atLeast } = useAuth();
  const { cycles, active, nameOf } = useCycles();
  const [cycleSetupOpen, setCycleSetupOpen] = React.useState(false);
  const [cycle, setCycle] = React.useState<string>("all");
  const [page, setPage] = React.useState(1);
  const [createOpen, setCreateOpen] = React.useState(false);

  const params = { page, page_size: PAGE_SIZE, ...(cycle !== "all" ? { cycle } : {}) };
  const { data, isLoading, isError, error, refetch } = useReviews(params);

  const columns = React.useMemo<ColumnDef<Review, unknown>[]>(
    () => [
      {
        accessorKey: "employee",
        header: "Employee",
        cell: ({ row }) => <PersonName id={row.original.employee} name={row.original.employee_name} withAvatar />,
      },
      {
        accessorKey: "reviewer",
        header: "Reviewer",
        cell: ({ row }) => <PersonName id={row.original.reviewer} name={row.original.reviewer_name} />,
      },
      {
        accessorKey: "cycle",
        header: "Cycle",
        cell: ({ row }) => <span className="text-muted-foreground">{row.original.cycle_name ?? nameOf(row.original.cycle)}</span>,
      },
      {
        accessorKey: "state",
        header: "State",
        cell: ({ row }) => <StatusBadge status={row.original.state} dot />,
      },
      {
        accessorKey: "source",
        header: "Source",
        cell: ({ row }) => <SourceBadge source={row.original.source} />,
      },
    ],
    [nameOf],
  );

  return (
    <div>
      <PageHeader
        eyebrow="Performance" title="Reviews"
        description="Performance reviews for your scope. Every AI draft passes a human approval gate before it's finalized."
        actions={
          atLeast("MANAGER") ? (
            <Button onClick={() => setCreateOpen(true)} disabled={!active}>
              <Plus className="h-4 w-4" />
              New review
            </Button>
          ) : undefined
        }
      />

      <div className="mb-4 flex items-center gap-2">
        <span className="text-xs font-medium text-muted-foreground">Cycle</span>
        <Select value={cycle} onValueChange={(v) => { setCycle(v); setPage(1); }}>
          <SelectTrigger className="w-52" aria-label="Filter by cycle"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All cycles</SelectItem>
            {cycles.map((c) => (
              <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <TableSkeleton rows={6} cols={5} />
      ) : isError ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : data && data.results.length > 0 ? (
        <DataTable
          mobilePrimary={["employee", "state", "cycle"]}
          mobileItemLabel="review"
          columns={columns}
          data={data.results}
          getRowId={(r) => r.id}
          onRowClick={(r) => navigate(`/reviews/${r.id}`)}
          pagination={{ page, pageSize: PAGE_SIZE, total: data.count, onPageChange: setPage }}
        />
      ) : (
        active ? (
          <EmptyState
            icon={FileText}
            title="No reviews yet"
            description="Create a review for someone on your team to start the cycle."
            action={atLeast("MANAGER") ? <Button onClick={() => setCreateOpen(true)}>New review</Button> : undefined}
          />
        ) : (
          // Without a cycle the "New review" button was simply HIDDEN, leaving
          // "create a review to start the cycle" above a panel with nothing to
          // click and no hint that a cycle was the missing piece.
          <SetupNeeded
            icon={FileText}
            title="Reviews start with a cycle"
            needs={{
              label: "a performance cycle",
              onFix: () => setCycleSetupOpen(true),
              canFix: atLeast("HRBP"),
            }}
            description="A review belongs to a period, and goals use the same one."
          />
        )
      )}

      <CycleSetupDialog open={cycleSetupOpen} onOpenChange={setCycleSetupOpen} />

      <CreateReviewDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        defaultCycle={active?.id}
        onCreated={(id) => navigate(`/reviews/${id}`)}
      />
    </div>
  );
}

function CreateReviewDialog({
  open,
  onOpenChange,
  defaultCycle,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  defaultCycle?: string;
  onCreated: (id: string) => void;
}) {
  const { cycles, active } = useCycles();
  // Only people the caller can actually create a review for (server scope rule) —
  // an out-of-subtree pick would 403 "outside your access scope" (FINAL D2).
  const people = useScopedPeople();
  const qc = useQueryClient();
  const [employee, setEmployee] = React.useState<string>("");
  const [cycle, setCycle] = React.useState<string>(defaultCycle ?? "");
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (open) {
      setEmployee("");
      setCycle(defaultCycle ?? active?.id ?? "");
      setError(null);
    }
  }, [open, defaultCycle, active]);

  const create = useMutation({
    mutationFn: () => reviewsApi.create({ employee, cycle }),
    onSuccess: (review) => {
      void qc.invalidateQueries({ queryKey: ["reviews", "list"] });
      notifySuccess("Review created");
      onOpenChange(false);
      onCreated(review.id);
    },
    onError: (err) => {
      setError(mapApiError(err).message);
      notifyError(err);
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>New review</DialogTitle>
          <DialogDescription>Reviews require an active cycle; you're set as the reviewer.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {error && <p className="text-sm text-danger">{error}</p>}
          <Field label="Employee" required>
            <Select value={employee} onValueChange={setEmployee}>
              <SelectTrigger><SelectValue placeholder="Select a report…" /></SelectTrigger>
              <SelectContent>
                {people.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.display}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Cycle" required>
            <Select value={cycle} onValueChange={setCycle}>
              <SelectTrigger><SelectValue placeholder="Select a cycle…" /></SelectTrigger>
              <SelectContent>
                {cycles.filter((c) => c.status === "ACTIVE").map((c) => (
                  <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={() => create.mutate()} loading={create.isPending} disabled={!employee || !cycle}>
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
