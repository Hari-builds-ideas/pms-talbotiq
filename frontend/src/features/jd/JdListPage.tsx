import * as React from "react";
import { useNavigate } from "react-router-dom";
import type { ColumnDef } from "@tanstack/react-table";
import { FilePlus2, Plus, ScrollText } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { DataTable } from "@/components/DataTable";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TableSkeleton } from "@/components/Skeletons";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { SourceBadge } from "@/components/Hitl";
import { PersonName } from "@/components/PersonName";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Field } from "@/components/Field";
import { useJdList, useJdMutations, useJdRequestMutations, useJdRequests } from "./useJd";
import { useAuth } from "@/lib/auth/AuthContext";
import { notifyError, notifySuccess } from "@/lib/toast";
import type { JdRequest, JobDescription } from "@/lib/types";

const PAGE = 50;

export function JdListPage() {
  const { atLeast } = useAuth();
  return (
    <div>
      <PageHeader
        eyebrow="Talent" title="JD Library"
        description="Versioned job descriptions with a human-gated lifecycle. Non-managers see published JDs only."
      />
      <Tabs defaultValue="library">
        <TabsList>
          <TabsTrigger value="library">Library</TabsTrigger>
          <TabsTrigger value="requests">Requests</TabsTrigger>
        </TabsList>
        <TabsContent value="library"><LibraryTab canAuthor={atLeast("HRBP")} /></TabsContent>
        <TabsContent value="requests"><RequestsTab /></TabsContent>
      </Tabs>
    </div>
  );
}

function LibraryTab({ canAuthor }: { canAuthor: boolean }) {
  const navigate = useNavigate();
  const [page, setPage] = React.useState(1);
  const list = useJdList({ page, page_size: PAGE });
  const { create } = useJdMutations();
  const [createOpen, setCreateOpen] = React.useState(false);

  const columns = React.useMemo<ColumnDef<JobDescription, unknown>[]>(
    () => [
      { accessorKey: "title", header: "Title", cell: ({ row }) => <span className="font-medium">{row.original.title}</span> },
      { accessorKey: "level", header: "Level" },
      { accessorKey: "department", header: "Department", cell: ({ row }) => <span className="text-muted-foreground">{row.original.department || "—"}</span> },
      { accessorKey: "status", header: "Status", cell: ({ row }) => <StatusBadge status={row.original.status} dot /> },
      { accessorKey: "source", header: "Source", cell: ({ row }) => <SourceBadge source={row.original.source} /> },
    ],
    [],
  );

  return (
    <div className="space-y-4">
      {canAuthor && (
        <div className="flex justify-end">
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> New JD
          </Button>
        </div>
      )}
      {list.isLoading ? (
        <TableSkeleton rows={5} cols={5} />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : list.data && list.data.results.length > 0 ? (
        <DataTable
          columns={columns}
          data={list.data.results}
          getRowId={(j) => j.id}
          onRowClick={(j) => navigate(`/jd/${j.id}`)}
          pagination={{ page, pageSize: PAGE, total: list.data.count, onPageChange: setPage }}
        />
      ) : (
        <EmptyState icon={ScrollText} title="No job descriptions" description={canAuthor ? "Create your first JD to start the library." : "No published JDs available."} action={canAuthor ? <Button onClick={() => setCreateOpen(true)}>New JD</Button> : undefined} />
      )}

      <CreateJdDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={(id) => navigate(`/jd/${id}`)}
        mutation={create}
      />
    </div>
  );
}

function CreateJdDialog({
  open,
  onOpenChange,
  onCreated,
  mutation,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onCreated: (id: string) => void;
  mutation: ReturnType<typeof useJdMutations>["create"];
}) {
  const [title, setTitle] = React.useState("");
  const [level, setLevel] = React.useState("");
  const [department, setDepartment] = React.useState("");

  React.useEffect(() => {
    if (open) { setTitle(""); setLevel(""); setDepartment(""); }
  }, [open]);

  async function submit() {
    try {
      const jd = await mutation.mutateAsync({ title: title.trim(), level: level.trim(), department: department.trim() });
      notifySuccess("JD created", "Add the body, then submit for review.");
      onOpenChange(false);
      onCreated(jd.id);
    } catch (err) {
      notifyError(err);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>New job description</DialogTitle>
          <DialogDescription>Starts as a draft (version 1).</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <Field label="Title" required><Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Staff Engineer" /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Level" required><Input value={level} onChange={(e) => setLevel(e.target.value)} placeholder="L5" /></Field>
            <Field label="Department"><Input value={department} onChange={(e) => setDepartment(e.target.value)} placeholder="Engineering" /></Field>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} loading={mutation.isPending} disabled={!title.trim() || !level.trim()}>Create</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RequestsTab() {
  const { atLeast } = useAuth();
  const [page, setPage] = React.useState(1);
  const requests = useJdRequests({ page, page_size: PAGE });
  const m = useJdRequestMutations();
  const [createOpen, setCreateOpen] = React.useState(false);
  const canFulfil = atLeast("HRBP");

  const columns = React.useMemo<ColumnDef<JdRequest, unknown>[]>(
    () => [
      { accessorKey: "title", header: "Title", cell: ({ row }) => <span className="font-medium">{row.original.title}</span> },
      { accessorKey: "level", header: "Level" },
      { accessorKey: "requested_by", header: "Requested by", cell: ({ row }) => <PersonName id={row.original.requested_by} name={row.original.requested_by_name} /> },
      { accessorKey: "notes", header: "Notes", cell: ({ row }) => <span className="text-muted-foreground">{row.original.notes || "—"}</span> },
      { accessorKey: "status", header: "Status", cell: ({ row }) => <StatusBadge status={row.original.status} /> },
      ...(canFulfil
        ? [
            {
              id: "actions",
              header: "",
              cell: ({ row }: { row: { original: JdRequest } }) => {
                const r = row.original;
                if (r.status !== "OPEN") return null;
                return (
                  <div className="flex justify-end gap-1.5">
                    <Button variant="outline" size="sm" onClick={() => m.fulfil.mutateAsync(r.id).then(() => notifySuccess("Marked fulfilled")).catch(notifyError)}>Fulfil</Button>
                    <Button variant="ghost" size="sm" className="text-danger" onClick={() => m.decline.mutateAsync(r.id).then(() => notifySuccess("Declined")).catch(notifyError)}>Decline</Button>
                  </div>
                );
              },
            } as ColumnDef<JdRequest, unknown>,
          ]
        : []),
    ],
    [canFulfil, m.fulfil, m.decline],
  );

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setCreateOpen(true)}>
          <FilePlus2 className="h-4 w-4" /> Request a JD
        </Button>
      </div>
      {requests.isLoading ? (
        <TableSkeleton rows={4} cols={5} />
      ) : requests.isError ? (
        <ErrorState error={requests.error} onRetry={() => requests.refetch()} />
      ) : requests.data && requests.data.results.length > 0 ? (
        <DataTable
          columns={columns}
          data={requests.data.results}
          getRowId={(r) => r.id}
          pagination={{ page, pageSize: PAGE, total: requests.data.count, onPageChange: setPage }}
        />
      ) : (
        <EmptyState icon={FilePlus2} title="No requests" description="Request a JD for a role you need authored." action={<Button onClick={() => setCreateOpen(true)}>Request a JD</Button>} />
      )}
      <CreateRequestDialog open={createOpen} onOpenChange={setCreateOpen} mutation={m.create} />
    </div>
  );
}

function CreateRequestDialog({
  open,
  onOpenChange,
  mutation,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  mutation: ReturnType<typeof useJdRequestMutations>["create"];
}) {
  const [title, setTitle] = React.useState("");
  const [level, setLevel] = React.useState("");
  const [notes, setNotes] = React.useState("");

  React.useEffect(() => {
    if (open) { setTitle(""); setLevel(""); setNotes(""); }
  }, [open]);

  async function submit() {
    try {
      await mutation.mutateAsync({ title: title.trim(), level: level.trim(), notes: notes.trim() });
      notifySuccess("Request submitted");
      onOpenChange(false);
    } catch (err) {
      notifyError(err);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Request a job description</DialogTitle>
          <DialogDescription>HRBP+ will author and publish it.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <Field label="Title" required><Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="SRE" /></Field>
          <Field label="Level"><Input value={level} onChange={(e) => setLevel(e.target.value)} placeholder="L4" /></Field>
          <Field label="Notes"><Textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Context for the role…" /></Field>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} loading={mutation.isPending} disabled={!title.trim()}>Submit request</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
