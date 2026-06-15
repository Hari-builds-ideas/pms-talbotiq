import * as React from "react";
import { Briefcase, GitBranch, Mail, ScrollText, Users } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
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
import { LinesSkeleton } from "@/components/Skeletons";
import { ErrorState } from "@/components/ErrorState";
import { usePerson, useOrgMutations } from "./useOrg";
import { useDirectory } from "@/lib/hooks/useDirectory";
import { useAuth } from "@/lib/auth/AuthContext";
import { ROLE_LABEL, type Role } from "@/lib/enums";
import { initials } from "@/lib/format";
import { mapApiError } from "@/lib/errors";
import { notifySuccess } from "@/lib/toast";

export function PersonSheet({
  personId,
  onOpenChange,
}: {
  personId: string | null;
  onOpenChange: (open: boolean) => void;
}) {
  const person = usePerson(personId);
  const { atLeast } = useAuth();
  const [reassignOpen, setReassignOpen] = React.useState(false);
  const p = person.data;

  return (
    <>
      <Sheet open={Boolean(personId)} onOpenChange={onOpenChange}>
        <SheetContent side="right" className="w-full sm:max-w-md">
          <SheetHeader>
            <SheetTitle>Person</SheetTitle>
            <SheetDescription>Profile, reporting line and positions.</SheetDescription>
          </SheetHeader>

          <div className="flex-1 overflow-y-auto scrollbar-thin p-5">
            {person.isLoading ? (
              <LinesSkeleton lines={6} />
            ) : person.isError ? (
              <ErrorState
                error={person.error}
                onBack={() => onOpenChange(false)}
                compact
              />
            ) : p ? (
              <div className="space-y-5">
                <div className="flex items-center gap-3">
                  <Avatar className="h-12 w-12">
                    <AvatarFallback>{initials(p.display)}</AvatarFallback>
                  </Avatar>
                  <div className="min-w-0">
                    <p className="truncate text-lg font-semibold">{p.display}</p>
                    <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
                      <Mail className="h-3.5 w-3.5" /> {p.email}
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  <Badge variant="secondary">{ROLE_LABEL[p.role as Role]}</Badge>
                  {p.title && <Badge variant="outline">{p.title}</Badge>}
                </div>

                <dl className="space-y-2.5 text-sm">
                  <Row label="Reports to" icon={GitBranch}>
                    {p.manager ? p.manager.display : <span className="text-muted-foreground">Top of tree</span>}
                  </Row>
                  <Row label="Direct reports" icon={Users}>{p.direct_reports}</Row>
                </dl>

                {p.filled_positions.length > 0 && (
                  <div>
                    <p className="mb-2 flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">
                      <Briefcase className="h-3.5 w-3.5" /> Positions
                    </p>
                    <ul className="space-y-1.5">
                      {p.filled_positions.map((pos) => (
                        <li key={pos.id} className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm">
                          <span>{pos.title}</span>
                          <span className="text-2xs text-muted-foreground">{pos.department}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {p.published_jds.length > 0 && (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <ScrollText className="h-4 w-4" />
                    {p.published_jds.length} linked job description{p.published_jds.length === 1 ? "" : "s"}
                  </div>
                )}
              </div>
            ) : null}
          </div>

          {p && atLeast("HRBP") && (
            <SheetFooter>
              <Button variant="outline" onClick={() => setReassignOpen(true)}>
                <GitBranch className="h-4 w-4" /> Reassign reporting line
              </Button>
            </SheetFooter>
          )}
        </SheetContent>
      </Sheet>

      {p && (
        <ReassignDialog
          open={reassignOpen}
          onOpenChange={setReassignOpen}
          employeeId={p.id}
          employeeName={p.display}
          currentManager={p.manager?.id ?? null}
        />
      )}
    </>
  );
}

function ReassignDialog({
  open,
  onOpenChange,
  employeeId,
  employeeName,
  currentManager,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  employeeId: string;
  employeeName: string;
  currentManager: string | null;
}) {
  const { nodes } = useDirectory();
  const { reassign } = useOrgMutations();
  const [manager, setManager] = React.useState<string>(currentManager ?? "none");
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (open) {
      setManager(currentManager ?? "none");
      setError(null);
    }
  }, [open, currentManager]);

  async function submit() {
    setError(null);
    try {
      await reassign.mutateAsync({ employee: employeeId, manager: manager === "none" ? null : manager });
      notifySuccess("Reporting line updated");
      onOpenChange(false);
    } catch (err) {
      const mapped = mapApiError(err);
      setError(
        mapped.code === "REPORTING_CYCLE"
          ? "That manager would create a reporting cycle. Choose someone outside this person's chain."
          : mapped.message,
      );
    }
  }

  const options = Object.values(nodes).filter((n) => n.id !== employeeId);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Reassign reporting line</DialogTitle>
          <DialogDescription>{employeeName} reports to…</DialogDescription>
        </DialogHeader>
        <Field label="New manager" error={error ?? undefined}>
          <Select value={manager} onValueChange={setManager}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="none">No manager (top of tree)</SelectItem>
              {options.map((n) => (
                <SelectItem key={n.id} value={n.id}>{n.display}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} loading={reassign.isPending}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Row({
  label,
  icon: Icon,
  children,
}: {
  label: string;
  icon: typeof Users;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="flex items-center gap-1.5 text-muted-foreground">
        <Icon className="h-3.5 w-3.5" /> {label}
      </dt>
      <dd className="font-medium">{children}</dd>
    </div>
  );
}
