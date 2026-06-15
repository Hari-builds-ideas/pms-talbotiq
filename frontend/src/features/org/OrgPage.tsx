import * as React from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Briefcase, MoreHorizontal, Network, Plus } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { DataTable } from "@/components/DataTable";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { TableSkeleton, LinesSkeleton } from "@/components/Skeletons";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { PersonName } from "@/components/PersonName";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { OrgTreeView } from "./OrgTreeView";
import { PersonSheet } from "./PersonSheet";
import { useOrgMutations, useOrgTree, usePositions, useVacancies } from "./useOrg";
import { useDirectory } from "@/lib/hooks/useDirectory";
import { useAuth } from "@/lib/auth/AuthContext";
import { useQuery } from "@tanstack/react-query";
import { jdApi } from "@/lib/api/endpoints";
import { notifyError, notifySuccess } from "@/lib/toast";
import { formatDate } from "@/lib/format";
import type { Position } from "@/lib/types";

export function OrgPage() {
  const { atLeast } = useAuth();
  const [selected, setSelected] = React.useState<string | null>(null);

  return (
    <div>
      <PageHeader
        title="Org Chart"
        description="Your reporting tree with headcount and vacancy rollups. Open a person for their profile and reporting line."
      />

      <Tabs defaultValue="tree">
        <TabsList>
          <TabsTrigger value="tree">Tree</TabsTrigger>
          <TabsTrigger value="positions">Positions</TabsTrigger>
          <TabsTrigger value="vacancies">Vacancies</TabsTrigger>
        </TabsList>

        <TabsContent value="tree">
          <TreeTab onSelect={setSelected} selectedId={selected} />
        </TabsContent>
        <TabsContent value="positions">
          <PositionsTab canManage={atLeast("HRBP")} />
        </TabsContent>
        <TabsContent value="vacancies">
          <VacanciesTab />
        </TabsContent>
      </Tabs>

      <PersonSheet personId={selected} onOpenChange={(o) => !o && setSelected(null)} />
    </div>
  );
}

function TreeTab({
  onSelect,
  selectedId,
}: {
  onSelect: (id: string) => void;
  selectedId: string | null;
}) {
  const tree = useOrgTree();
  return (
    <Panel title="Reporting tree" icon={Network}>
      {tree.isLoading ? (
        <LinesSkeleton lines={8} />
      ) : tree.isError ? (
        <ErrorState error={tree.error} onRetry={() => tree.refetch()} compact />
      ) : tree.data && tree.data.roots.length > 0 ? (
        <OrgTreeView tree={tree.data} selectedId={selectedId} onSelect={onSelect} />
      ) : (
        <EmptyState compact icon={Network} title="No org data" description="No reporting structure in your scope yet." />
      )}
    </Panel>
  );
}

const POS_PAGE = 50;

function PositionsTab({ canManage }: { canManage: boolean }) {
  const [page, setPage] = React.useState(1);
  const positions = usePositions({ page, page_size: POS_PAGE });
  const m = useOrgMutations();
  const [createOpen, setCreateOpen] = React.useState(false);
  const [fillTarget, setFillTarget] = React.useState<Position | null>(null);
  const [linkTarget, setLinkTarget] = React.useState<Position | null>(null);
  const [closeTarget, setCloseTarget] = React.useState<Position | null>(null);

  const columns = React.useMemo<ColumnDef<Position, unknown>[]>(
    () => [
      { accessorKey: "title", header: "Title", cell: ({ row }) => <span className="font-medium">{row.original.title}</span> },
      { accessorKey: "department", header: "Department", cell: ({ row }) => <span className="text-muted-foreground">{row.original.department || "—"}</span> },
      { accessorKey: "reports_to", header: "Reports to", cell: ({ row }) => <PersonName id={row.original.reports_to} /> },
      { accessorKey: "status", header: "Status", cell: ({ row }) => <StatusBadge status={row.original.status} dot /> },
      { accessorKey: "filled_by", header: "Filled by", cell: ({ row }) => (row.original.filled_by ? <PersonName id={row.original.filled_by} /> : <span className="text-muted-foreground">—</span>) },
      {
        id: "jd",
        header: "JD",
        cell: ({ row }) => (row.original.published_jd ? <Badge variant="info">Linked</Badge> : <span className="text-2xs text-muted-foreground">—</span>),
      },
      ...(canManage
        ? [
            {
              id: "actions",
              header: "",
              cell: ({ row }: { row: { original: Position } }) => {
                const p = row.original;
                return (
                  <div className="flex justify-end">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon-sm" aria-label="Position actions">
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        {p.status === "OPEN" && <DropdownMenuItem onClick={() => setFillTarget(p)}>Fill position</DropdownMenuItem>}
                        {p.published_jd ? (
                          <DropdownMenuItem onClick={() => m.unlinkJd.mutate(p.id)}>Unlink JD</DropdownMenuItem>
                        ) : (
                          <DropdownMenuItem onClick={() => setLinkTarget(p)}>Link published JD</DropdownMenuItem>
                        )}
                        {p.status !== "CLOSED" && (
                          <>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem className="text-danger focus:text-danger" onClick={() => setCloseTarget(p)}>
                              Close position
                            </DropdownMenuItem>
                          </>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                );
              },
            } as ColumnDef<Position, unknown>,
          ]
        : []),
    ],
    [canManage, m.unlinkJd],
  );

  return (
    <div className="space-y-4">
      {canManage && (
        <div className="flex justify-end">
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> Create position
          </Button>
        </div>
      )}
      {positions.isLoading ? (
        <TableSkeleton rows={5} cols={6} />
      ) : positions.isError ? (
        <ErrorState error={positions.error} onRetry={() => positions.refetch()} />
      ) : positions.data && positions.data.results.length > 0 ? (
        <DataTable
          columns={columns}
          data={positions.data.results}
          getRowId={(p) => p.id}
          pagination={{ page, pageSize: POS_PAGE, total: positions.data.count, onPageChange: setPage }}
        />
      ) : (
        <EmptyState icon={Briefcase} title="No positions" description="Create a position to track open roles and vacancies." />
      )}

      <CreatePositionDialog open={createOpen} onOpenChange={setCreateOpen} mutation={m.createPosition} />
      {fillTarget && <FillDialog position={fillTarget} onClose={() => setFillTarget(null)} mutation={m.fill} />}
      {linkTarget && <LinkJdDialog position={linkTarget} onClose={() => setLinkTarget(null)} mutation={m.linkJd} />}
      {closeTarget && (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setCloseTarget(null)}
          title="Close this position?"
          description={`"${closeTarget.title}" will be marked closed.`}
          confirmLabel="Close position"
          destructive
          onConfirm={async () => {
            await m.close.mutateAsync(closeTarget.id);
            notifySuccess("Position closed");
            setCloseTarget(null);
          }}
        />
      )}
    </div>
  );
}

function VacanciesTab() {
  const vacancies = useVacancies();
  return (
    <Panel title="Open vacancies" icon={Briefcase}>
      {vacancies.isLoading ? (
        <LinesSkeleton lines={4} />
      ) : vacancies.isError ? (
        <ErrorState error={vacancies.error} onRetry={() => vacancies.refetch()} compact />
      ) : vacancies.data && vacancies.data.length > 0 ? (
        <ul className="divide-y divide-border">
          {vacancies.data.map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
              <div>
                <p className="text-sm font-medium">{p.title}</p>
                <p className="text-2xs text-muted-foreground">
                  {p.department || "—"} · reports to <PersonName id={p.reports_to} /> · opened {formatDate(p.opened_at)}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {p.published_jd && <Badge variant="info">JD linked</Badge>}
                <StatusBadge status={p.status} />
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState compact icon={Briefcase} title="No open vacancies" description="Every position in your scope is filled or closed." />
      )}
    </Panel>
  );
}

// ---- dialogs ---------------------------------------------------------------

function CreatePositionDialog({
  open,
  onOpenChange,
  mutation,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  mutation: ReturnType<typeof useOrgMutations>["createPosition"];
}) {
  const { nodes } = useDirectory();
  const people = Object.values(nodes);
  const [title, setTitle] = React.useState("");
  const [department, setDepartment] = React.useState("");
  const [reportsTo, setReportsTo] = React.useState<string>("none");

  React.useEffect(() => {
    if (open) { setTitle(""); setDepartment(""); setReportsTo("none"); }
  }, [open]);

  async function submit() {
    try {
      await mutation.mutateAsync({ title: title.trim(), department: department.trim(), reports_to: reportsTo === "none" ? null : reportsTo });
      notifySuccess("Position created");
      onOpenChange(false);
    } catch (err) {
      notifyError(err);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Create position</DialogTitle>
          <DialogDescription>New positions open as a vacancy.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <Field label="Title" required>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Senior Engineer" />
          </Field>
          <Field label="Department">
            <Input value={department} onChange={(e) => setDepartment(e.target.value)} placeholder="Engineering" />
          </Field>
          <Field label="Reports to">
            <Select value={reportsTo} onValueChange={setReportsTo}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">No manager</SelectItem>
                {people.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.display}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} loading={mutation.isPending} disabled={!title.trim()}>Create</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function FillDialog({
  position,
  onClose,
  mutation,
}: {
  position: Position;
  onClose: () => void;
  mutation: ReturnType<typeof useOrgMutations>["fill"];
}) {
  const { nodes } = useDirectory();
  const people = Object.values(nodes);
  const [person, setPerson] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  async function submit() {
    setError(null);
    try {
      await mutation.mutateAsync({ id: position.id, filled_by: person });
      notifySuccess("Position filled");
      onClose();
    } catch (err) {
      notifyError(err);
      onClose();
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Fill position</DialogTitle>
          <DialogDescription>{position.title}</DialogDescription>
        </DialogHeader>
        <Field label="Filled by" required error={error ?? undefined}>
          <Select value={person} onValueChange={setPerson}>
            <SelectTrigger><SelectValue placeholder="Select a person…" /></SelectTrigger>
            <SelectContent>
              {people.map((p) => (
                <SelectItem key={p.id} value={p.id}>{p.display}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} loading={mutation.isPending} disabled={!person}>Fill</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function LinkJdDialog({
  position,
  onClose,
  mutation,
}: {
  position: Position;
  onClose: () => void;
  mutation: ReturnType<typeof useOrgMutations>["linkJd"];
}) {
  const published = useQuery({
    queryKey: ["jd", "published-for-link"],
    queryFn: () => jdApi.list({ page_size: 200 }),
  });
  const options = (published.data?.results ?? []).filter((j) => j.status === "PUBLISHED");
  const [jd, setJd] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  async function submit() {
    setError(null);
    try {
      await mutation.mutateAsync({ id: position.id, jd });
      notifySuccess("JD linked");
      onClose();
    } catch (err) {
      notifyError(err);
      onClose();
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Link a published JD</DialogTitle>
          <DialogDescription>{position.title} — only published JDs can be linked.</DialogDescription>
        </DialogHeader>
        <Field label="Job description" error={error ?? undefined}>
          {published.isLoading ? (
            <LinesSkeleton lines={2} />
          ) : options.length === 0 ? (
            <p className="text-sm text-muted-foreground">No published JDs available to link.</p>
          ) : (
            <Select value={jd} onValueChange={setJd}>
              <SelectTrigger><SelectValue placeholder="Select a JD…" /></SelectTrigger>
              <SelectContent>
                {options.map((j) => (
                  <SelectItem key={j.id} value={j.id}>{j.title} · {j.level}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </Field>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} loading={mutation.isPending} disabled={!jd}>Link JD</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
