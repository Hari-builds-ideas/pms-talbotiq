import * as React from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { MoreHorizontal, ShieldCheck, UserPlus } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { DataTable } from "@/components/DataTable";
import { TableSkeleton } from "@/components/Skeletons";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Field } from "@/components/Field";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useUserMutations, useUsers } from "./useAdmin";
import { ROLES, ROLE_LABEL, type Role } from "@/lib/enums";
import { mapApiError } from "@/lib/errors";
import { notifySuccess } from "@/lib/toast";
import { initials } from "@/lib/format";
import type { AdminUser } from "@/lib/types";

export function UsersPage() {
  const { data: users, isLoading, isError, error, refetch } = useUsers();
  const [createOpen, setCreateOpen] = React.useState(false);
  const [roleTarget, setRoleTarget] = React.useState<AdminUser | null>(null);
  const [lineTarget, setLineTarget] = React.useState<AdminUser | null>(null);
  const [nameTarget, setNameTarget] = React.useState<AdminUser | null>(null);
  const [activeTarget, setActiveTarget] = React.useState<AdminUser | null>(null);
  const m = useUserMutations();

  const activeUsers = users?.filter((u) => u.is_active) ?? [];

  const columns = React.useMemo<ColumnDef<AdminUser, unknown>[]>(
    () => [
      {
        accessorKey: "display",
        header: "User",
        cell: ({ row }) => {
          const u = row.original;
          return (
            <div className="flex items-center gap-2.5">
              <Avatar className="h-8 w-8">
                <AvatarFallback>{initials(u.display)}</AvatarFallback>
              </Avatar>
              <div className="min-w-0">
                <div className="truncate font-medium text-foreground">{u.display}</div>
                <div className="truncate text-2xs text-muted-foreground">{u.email}</div>
              </div>
            </div>
          );
        },
      },
      {
        accessorKey: "role",
        header: "Role",
        cell: ({ row }) => <Badge variant="secondary">{ROLE_LABEL[row.original.role]}</Badge>,
      },
      {
        accessorKey: "manager",
        header: "Manager",
        cell: ({ row }) => {
          const mgr = users?.find((x) => x.id === row.original.manager);
          return <span className="text-muted-foreground">{mgr?.display ?? "—"}</span>;
        },
      },
      {
        accessorKey: "is_active",
        header: "Status",
        cell: ({ row }) => (
          <StatusBadge status={row.original.is_active ? "ACTIVE" : "SUSPENDED"} dot />
        ),
      },
      {
        id: "mfa",
        header: "MFA",
        cell: ({ row }) =>
          row.original.mfa_enabled ? (
            <Badge variant="success" className="gap-1">
              <ShieldCheck className="h-3 w-3" /> On
            </Badge>
          ) : (
            <span className="text-2xs text-muted-foreground">Off</span>
          ),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => {
          const u = row.original;
          return (
            <div className="flex justify-end">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon-sm" aria-label="User actions">
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => setRoleTarget(u)}>Change role</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setLineTarget(u)}>Set reporting line</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setNameTarget(u)}>Edit display name</DropdownMenuItem>
                  <DropdownMenuSeparator />
                  {u.is_active ? (
                    <DropdownMenuItem
                      className="text-danger focus:text-danger"
                      onClick={() => setActiveTarget(u)}
                    >
                      Deactivate
                    </DropdownMenuItem>
                  ) : (
                    <DropdownMenuItem onClick={() => setActiveTarget(u)}>Reactivate</DropdownMenuItem>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          );
        },
      },
    ],
    [users],
  );

  return (
    <div>
      <PageHeader
        title="Users & Roles"
        description="Manage tenant users, roles and reporting lines. Names fall back to email until a display name is set."
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <UserPlus className="h-4 w-4" />
            Create user
          </Button>
        }
      />

      {isLoading ? (
        <TableSkeleton rows={6} cols={6} />
      ) : isError ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : !users || users.length === 0 ? (
        <EmptyState
          icon={UserPlus}
          title="No users yet"
          description="Create your first user to start building the org."
          action={<Button onClick={() => setCreateOpen(true)}>Create user</Button>}
        />
      ) : (
        <DataTable columns={columns} data={users} getRowId={(u) => u.id} />
      )}

      <CreateUserDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        managers={activeUsers}
        mutation={m.create}
      />
      {roleTarget && (
        <RoleDialog
          user={roleTarget}
          onClose={() => setRoleTarget(null)}
          mutation={m.setRole}
        />
      )}
      {lineTarget && (
        <ReportingLineDialog
          user={lineTarget}
          users={activeUsers}
          onClose={() => setLineTarget(null)}
          mutation={m.setReportingLine}
        />
      )}
      {nameTarget && (
        <DisplayNameDialog
          user={nameTarget}
          onClose={() => setNameTarget(null)}
          mutation={m.setDisplayName}
        />
      )}
      {activeTarget && (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setActiveTarget(null)}
          title={activeTarget.is_active ? "Deactivate user?" : "Reactivate user?"}
          description={
            activeTarget.is_active
              ? `${activeTarget.display} will lose access until reactivated.`
              : `${activeTarget.display} will regain access.`
          }
          confirmLabel={activeTarget.is_active ? "Deactivate" : "Reactivate"}
          destructive={activeTarget.is_active}
          onConfirm={async () => {
            const fn = activeTarget.is_active ? m.deactivate : m.reactivate;
            await fn.mutateAsync(activeTarget.id);
            notifySuccess(activeTarget.is_active ? "User deactivated" : "User reactivated");
            setActiveTarget(null);
          }}
        />
      )}
    </div>
  );
}

// ---- dialogs ---------------------------------------------------------------

function CreateUserDialog({
  open,
  onOpenChange,
  managers,
  mutation,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  managers: AdminUser[];
  mutation: ReturnType<typeof useUserMutations>["create"];
}) {
  const [email, setEmail] = React.useState("");
  const [displayName, setDisplayName] = React.useState("");
  const [role, setRole] = React.useState<Role>("EMPLOYEE");
  const [manager, setManager] = React.useState<string>("none");
  const [formError, setFormError] = React.useState<string | null>(null);
  const [emailError, setEmailError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (open) {
      setEmail(""); setDisplayName(""); setRole("EMPLOYEE"); setManager("none");
      setFormError(null); setEmailError(null);
    }
  }, [open]);

  async function submit() {
    setFormError(null);
    setEmailError(null);
    if (!email.trim() || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      setEmailError("Enter a valid email.");
      return;
    }
    try {
      await mutation.mutateAsync({
        email: email.trim(),
        role,
        manager: manager === "none" ? null : manager,
        display_name: displayName.trim() || null,
      });
      notifySuccess("User created");
      onOpenChange(false);
    } catch (err) {
      const mapped = mapApiError(err);
      if (mapped.code === "EMAIL_TAKEN") setEmailError(mapped.message);
      else setFormError(mapped.message);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create user</DialogTitle>
          <DialogDescription>Add a user to the Acme Corp tenant.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {formError && (
            <p className="rounded-md bg-danger-subtle px-3 py-2 text-sm text-danger">{formError}</p>
          )}
          <Field label="Email" required error={emailError ?? undefined}>
            <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="person@acme.test" />
          </Field>
          <Field label="Display name" hint="Optional — falls back to email.">
            <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Jane Doe" />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Role" required>
              <Select value={role} onValueChange={(v) => setRole(v as Role)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {ROLES.map((r) => (
                    <SelectItem key={r} value={r}>{ROLE_LABEL[r]}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Manager">
              <Select value={manager} onValueChange={setManager}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">No manager</SelectItem>
                  {managers.map((mgr) => (
                    <SelectItem key={mgr.id} value={mgr.id}>{mgr.display}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} loading={mutation.isPending}>Create user</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RoleDialog({
  user,
  onClose,
  mutation,
}: {
  user: AdminUser;
  onClose: () => void;
  mutation: ReturnType<typeof useUserMutations>["setRole"];
}) {
  const [role, setRole] = React.useState<Role>(user.role);
  const [error, setError] = React.useState<string | null>(null);

  async function submit() {
    setError(null);
    try {
      await mutation.mutateAsync({ id: user.id, role });
      notifySuccess(`Role updated to ${ROLE_LABEL[role]}`);
      onClose();
    } catch (err) {
      setError(mapApiError(err).message);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Change role</DialogTitle>
          <DialogDescription>{user.display}</DialogDescription>
        </DialogHeader>
        <Field label="Role" error={error ?? undefined}>
          <Select value={role} onValueChange={(v) => setRole(v as Role)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {ROLES.map((r) => (
                <SelectItem key={r} value={r}>{ROLE_LABEL[r]}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} loading={mutation.isPending} disabled={role === user.role}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ReportingLineDialog({
  user,
  users,
  onClose,
  mutation,
}: {
  user: AdminUser;
  users: AdminUser[];
  onClose: () => void;
  mutation: ReturnType<typeof useUserMutations>["setReportingLine"];
}) {
  const [manager, setManager] = React.useState<string>(user.manager ?? "none");
  const [error, setError] = React.useState<string | null>(null);

  async function submit() {
    setError(null);
    try {
      await mutation.mutateAsync({ id: user.id, manager: manager === "none" ? null : manager });
      notifySuccess("Reporting line updated");
      onClose();
    } catch (err) {
      const mapped = mapApiError(err);
      setError(
        mapped.code === "REPORTING_CYCLE"
          ? "That manager would create a reporting cycle. Choose someone outside this person's chain."
          : mapped.message,
      );
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Set reporting line</DialogTitle>
          <DialogDescription>{user.display} reports to…</DialogDescription>
        </DialogHeader>
        <Field label="Manager" error={error ?? undefined}>
          <Select value={manager} onValueChange={setManager}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="none">No manager (top of tree)</SelectItem>
              {users
                .filter((u) => u.id !== user.id)
                .map((u) => (
                  <SelectItem key={u.id} value={u.id}>{u.display}</SelectItem>
                ))}
            </SelectContent>
          </Select>
        </Field>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} loading={mutation.isPending}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DisplayNameDialog({
  user,
  onClose,
  mutation,
}: {
  user: AdminUser;
  onClose: () => void;
  mutation: ReturnType<typeof useUserMutations>["setDisplayName"];
}) {
  const [name, setName] = React.useState(user.display_name ?? "");

  async function submit() {
    await mutation.mutateAsync({ id: user.id, display_name: name.trim() || null });
    notifySuccess("Display name updated");
    onClose();
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Edit display name</DialogTitle>
          <DialogDescription>Leave blank to fall back to {user.email}.</DialogDescription>
        </DialogHeader>
        <Field label="Display name">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={user.email} autoFocus />
        </Field>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} loading={mutation.isPending}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
