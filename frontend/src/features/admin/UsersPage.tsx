import * as React from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { MoreHorizontal, Search, ShieldCheck, Upload, UserPlus, X } from "lucide-react";
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
import { useDirectory } from "@/lib/hooks/useDirectory";
import { useDebouncedValue } from "@/lib/hooks/useDebouncedValue";
import { ROLES, ROLE_LABEL, type Role } from "@/lib/enums";
import { mapApiError } from "@/lib/errors";
import { notifyError, notifySuccess } from "@/lib/toast";
import { initials } from "@/lib/format";
import { adminApi } from "@/lib/api/endpoints";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { AdminUser } from "@/lib/types";

/** Minimal person option for the manager dropdowns (sourced from the directory). */
interface PersonOption {
  id: string;
  display: string;
}

const PAGE = 50;

export function UsersPage() {
  const [page, setPage] = React.useState(1);
  const [search, setSearch] = React.useState("");
  const debouncedSearch = useDebouncedValue(search.trim(), 300);
  // A new search starts at page 1 (otherwise you can land on an out-of-range page).
  React.useEffect(() => setPage(1), [debouncedSearch]);

  const { data, isLoading, isError, error, refetch } = useUsers({
    page,
    page_size: PAGE,
    ...(debouncedSearch ? { search: debouncedSearch } : {}),
  });
  const rows = data?.results ?? [];

  // Manager names + manager dropdowns come from the (tenant-wide, active-only)
  // directory, not the paginated page — so they resolve regardless of which page
  // a row's manager happens to fall on.
  const { nameOf, nodes } = useDirectory();
  const people: PersonOption[] = Object.values(nodes);

  const [createOpen, setCreateOpen] = React.useState(false);
  const [roleTarget, setRoleTarget] = React.useState<AdminUser | null>(null);
  const [lineTarget, setLineTarget] = React.useState<AdminUser | null>(null);
  const [nameTarget, setNameTarget] = React.useState<AdminUser | null>(null);
  const [activeTarget, setActiveTarget] = React.useState<AdminUser | null>(null);
  const m = useUserMutations();

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
        cell: ({ row }) => (
          <span className="text-muted-foreground">
            {row.original.manager ? nameOf(row.original.manager) : "—"}
          </span>
        ),
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
    [nameOf],
  );

  return (
    <div>
      <PageHeader
        eyebrow="Settings" title="Users & Roles"
        description="Manage tenant users, roles and reporting lines. Names fall back to email until a display name is set."
        actions={
          <div className="flex items-center gap-2">
            <ImportCsvButton />
            <InviteDialog />
            <Button onClick={() => setCreateOpen(true)}>
              <UserPlus className="h-4 w-4" />
              Create user
            </Button>
          </div>
        }
      />

      <div className="mb-4 max-w-sm">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name, email or role…"
            className="pl-9 pr-9"
            aria-label="Search users"
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch("")}
              aria-label="Clear search"
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {isLoading ? (
        <TableSkeleton rows={6} cols={6} />
      ) : isError ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : rows.length === 0 ? (
        debouncedSearch ? (
          <EmptyState
            icon={Search}
            title="No matching users"
            description="Try a different name, email or role."
            action={<Button variant="outline" onClick={() => setSearch("")}>Clear search</Button>}
          />
        ) : (
          <EmptyState
            icon={UserPlus}
            title="No users yet"
            description="Create your first user to start building the org."
            action={<Button onClick={() => setCreateOpen(true)}>Create user</Button>}
          />
        )
      ) : (
        <DataTable
          columns={columns}
          data={rows}
          getRowId={(u) => u.id}
          pagination={{ page, pageSize: PAGE, total: data?.count ?? 0, onPageChange: setPage }}
        />
      )}

      <CreateUserDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        managers={people}
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
          users={people}
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
  managers: PersonOption[];
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
  users: PersonOption[];
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

/** PHASE2 L1.2 — invite a user by email (the B2B onboarding path). Shows the
 *  invite link for copy-paste (works even without SMTP) + pending invites. */
/** Bulk employee onboarding (PROD_B): upload a CSV, see a per-row result summary.
 *  Idempotent on the server (upsert by email); seats + role ceiling enforced there. */
function ImportCsvButton() {
  const qc = useQueryClient();
  const [open, setOpen] = React.useState(false);
  const [file, setFile] = React.useState<File | null>(null);
  const [result, setResult] = React.useState<Awaited<
    ReturnType<typeof adminApi.bulkImport>
  > | null>(null);

  const importMut = useMutation({
    mutationFn: () => adminApi.bulkImport(file as File),
    onSuccess: (r) => {
      setResult(r);
      notifySuccess(
        "Import finished",
        `${r.created} created · ${r.updated} updated · ${r.skipped} skipped`,
      );
      void qc.invalidateQueries({ queryKey: ["admin", "users"] });
      void qc.invalidateQueries({ queryKey: ["directory"] });
    },
    onError: (e: unknown) => notifyError(e),
  });

  function reset() {
    setFile(null);
    setResult(null);
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) reset();
      }}
    >
      <Button variant="outline" onClick={() => setOpen(true)}>
        <Upload className="h-4 w-4" />
        Import CSV
      </Button>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Bulk import employees</DialogTitle>
          <DialogDescription>
            Upload a CSV with a header row:{" "}
            <code className="text-xs">name,email,role,department,designation,manager</code>. The
            manager column is the manager's email. Re-importing updates existing people
            (matched by email) — it never creates duplicates. Imported people sign in with
            Google/SSO, or set a password via "Forgot password".
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <input
            type="file"
            accept=".csv,text/csv"
            aria-label="CSV file"
            onChange={(e) => {
              setResult(null);
              setFile(e.target.files?.[0] ?? null);
            }}
            className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-secondary file:px-3 file:py-1.5 file:text-sm file:font-medium"
          />

          {result && (
            <div className="rounded-lg border border-border bg-secondary/40 p-3 text-sm">
              <p className="font-medium">
                {result.created} created · {result.updated} updated · {result.skipped} skipped
                <span className="text-muted-foreground"> (of {result.total})</span>
              </p>
              {result.errors.length > 0 && (
                <ul className="mt-2 max-h-40 space-y-1 overflow-y-auto scrollbar-thin text-xs text-danger">
                  {result.errors.map((er, i) => (
                    <li key={i}>
                      Row {er.row}
                      {er.email ? ` (${er.email})` : ""}: {er.error}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Close
          </Button>
          <Button
            onClick={() => importMut.mutate()}
            loading={importMut.isPending}
            disabled={!file}
          >
            Import
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function InviteDialog() {
  const qc = useQueryClient();
  const [open, setOpen] = React.useState(false);
  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState<Role>("EMPLOYEE");
  const [lastUrl, setLastUrl] = React.useState<string | null>(null);
  const invitesQ = useQuery({
    queryKey: ["admin", "invitations"],
    queryFn: adminApi.invitations,
    enabled: open,
  });
  const refresh = () => void qc.invalidateQueries({ queryKey: ["admin", "invitations"] });
  const invite = useMutation({
    mutationFn: () => adminApi.invite({ email: email.trim(), role }),
    onSuccess: (r) => {
      setLastUrl(r.invite_url);
      notifySuccess(
        r.emailed ? "Invitation emailed" : "Invitation created",
        r.emailed ? "You can also copy the link below." : "Email isn't configured — copy the link below.",
      );
      setEmail("");
      refresh();
    },
    onError: (e: unknown) => notifyError(e),
  });
  const revoke = useMutation({
    mutationFn: (id: string) => adminApi.inviteRevoke(id),
    onSuccess: () => {
      notifySuccess("Invitation revoked");
      refresh();
    },
    onError: (e: unknown) => notifyError(e),
  });
  const resend = useMutation({
    mutationFn: (id: string) => adminApi.inviteResend(id),
    onSuccess: (r) => {
      setLastUrl(r.invite_url);
      notifySuccess(
        r.emailed ? "Invitation re-sent" : "New link ready",
        r.emailed ? "A fresh link was emailed — it's also below." : "Email isn't configured — copy the fresh link below.",
      );
      refresh();
    },
    onError: (e: unknown) => notifyError(e),
  });
  const pending = (invitesQ.data ?? []).filter((i) => i.status === "PENDING");

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button variant="outline" onClick={() => setOpen(true)}>
        Invite user
      </Button>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Invite a user</DialogTitle>
          <DialogDescription>
            They'll get a link to set their password and join this workspace with the assigned role.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="flex gap-2">
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="person@company.com"
              aria-label="Invite email"
            />
            <Select value={role} onValueChange={(v) => setRole(v as Role)}>
              <SelectTrigger className="w-36" aria-label="Invite role"><SelectValue /></SelectTrigger>
              <SelectContent>
                {ROLES.map((r) => (
                  <SelectItem key={r} value={r}>{ROLE_LABEL[r]}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button onClick={() => invite.mutate()} loading={invite.isPending} disabled={!email.trim()}>
              Send
            </Button>
          </div>
          {lastUrl && (
            <div className="space-y-1 rounded-md bg-secondary/40 p-2">
              <p className="text-2xs font-semibold uppercase tracking-wide text-muted-foreground">Invite link</p>
              <p className="break-all font-mono text-xs">{lastUrl}</p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  void navigator.clipboard?.writeText(lastUrl);
                  notifySuccess("Link copied");
                }}
              >
                Copy link
              </Button>
            </div>
          )}
          <div>
            <p className="mb-1 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">
              Pending invitations
            </p>
            {pending.length === 0 ? (
              <p className="text-xs text-muted-foreground">None.</p>
            ) : (
              <ul className="divide-y divide-border">
                {pending.map((i) => (
                  <li key={i.id} className="flex items-center justify-between gap-2 py-1.5 text-xs">
                    <span className="truncate">
                      {i.email} <Badge variant="muted" className="ml-1">{ROLE_LABEL[i.role]}</Badge>
                    </span>
                    <span className="flex shrink-0 items-center">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => resend.mutate(i.id)}
                        disabled={resend.isPending}
                      >
                        Resend
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-danger"
                        onClick={() => revoke.mutate(i.id)}
                      >
                        Revoke
                      </Button>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
