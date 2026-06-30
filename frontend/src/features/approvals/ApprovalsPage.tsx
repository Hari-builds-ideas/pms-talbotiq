import * as React from "react";
import {
  ClipboardCheck,
  GitBranch,
  Inbox,
  Plus,
  Workflow as WorkflowIcon,
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { LinesSkeleton } from "@/components/Skeletons";
import { useAuth } from "@/lib/auth/AuthContext";
import { humanize, ROLE_LABEL, type Role } from "@/lib/enums";
import { formatRelative, isOverdue } from "@/lib/format";
import { useInbox, useWorkflowMutations, useWorkflows } from "./useApprovals";
import { RouteSheet } from "./RouteSheet";
import { WorkflowDialog } from "./WorkflowDialog";
import { notifyError, notifySuccess } from "@/lib/toast";
import type { ApprovalWorkflow } from "@/lib/types";

export function ApprovalsPage() {
  const { atLeast } = useAuth();
  const canConfigure = atLeast("HRBP");
  const [active, setActive] = React.useState<{ routeId: string; stepId: string } | null>(null);

  return (
    <div>
      <PageHeader
        eyebrow="Performance" title="Approvals"
        description="Act on steps assigned to you, track routes, and (HRBP+) design approval workflows."
      />

      <Tabs defaultValue="inbox">
        <TabsList>
          <TabsTrigger value="inbox">Inbox</TabsTrigger>
          {canConfigure && <TabsTrigger value="designer">Workflow designer</TabsTrigger>}
        </TabsList>

        <TabsContent value="inbox">
          <InboxTab onOpen={(routeId, stepId) => setActive({ routeId, stepId })} />
        </TabsContent>

        {canConfigure && (
          <TabsContent value="designer">
            <DesignerTab />
          </TabsContent>
        )}
      </Tabs>

      <RouteSheet
        routeId={active?.routeId ?? null}
        actionStepId={active?.stepId}
        onOpenChange={(open) => !open && setActive(null)}
      />
    </div>
  );
}

function InboxTab({ onOpen }: { onOpen: (routeId: string, stepId: string) => void }) {
  const inbox = useInbox();

  return (
    <Panel title="Awaiting your decision" icon={ClipboardCheck}>
      {inbox.isLoading ? (
        <LinesSkeleton lines={4} />
      ) : inbox.isError ? (
        <ErrorState error={inbox.error} onRetry={() => inbox.refetch()} compact />
      ) : inbox.data && inbox.data.length > 0 ? (
        <ul className="divide-y divide-border">
          {inbox.data.map((item) => {
            const overdue = isOverdue(item.due_at);
            return (
              <li key={item.id} className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
                <div className="min-w-0">
                  <p className="flex items-center gap-2 text-sm font-medium">
                    {humanize(item.artifact_type)} approval
                    <span className="font-normal text-muted-foreground">step {item.order}</span>
                    {item.escalated && <Badge variant="warning">Escalated</Badge>}
                    {overdue && <Badge variant="danger">Overdue</Badge>}
                  </p>
                  <p className="text-2xs text-muted-foreground">
                    As {item.approver_role ? ROLE_LABEL[item.approver_role as Role] : "approver"} · due{" "}
                    {formatRelative(item.due_at)}
                  </p>
                </div>
                <Button variant="outline" size="sm" onClick={() => onOpen(item.route, item.id)}>
                  Review
                </Button>
              </li>
            );
          })}
        </ul>
      ) : (
        <EmptyState
          compact
          icon={Inbox}
          title="Inbox zero"
          description="No approval steps are waiting on you. Steps appear here when a route reaches a step assigned to your role."
        />
      )}
    </Panel>
  );
}

function DesignerTab() {
  const workflows = useWorkflows();
  const { activate, deactivate } = useWorkflowMutations();
  const [createOpen, setCreateOpen] = React.useState(false);

  async function toggle(wf: ApprovalWorkflow) {
    try {
      if (wf.active) {
        await deactivate.mutateAsync(wf.id);
        notifySuccess("Workflow deactivated");
      } else {
        await activate.mutateAsync(wf.id);
        notifySuccess("Workflow activated");
      }
    } catch (err) {
      notifyError(err);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          At most one workflow can be active per artifact type. To change steps, create a new workflow
          (steps are fixed at creation; in-flight routes are snapshotted).
        </p>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4" />
          Create workflow
        </Button>
      </div>

      {workflows.isLoading ? (
        <LinesSkeleton lines={5} />
      ) : workflows.isError ? (
        <ErrorState error={workflows.error} onRetry={() => workflows.refetch()} />
      ) : workflows.data && workflows.data.length > 0 ? (
        <div className="space-y-3">
          {workflows.data.map((wf) => (
            <Panel
              key={wf.id}
              title={wf.name}
              icon={WorkflowIcon}
              aside={
                <span className="flex items-center gap-2">
                  <Badge variant="outline">{humanize(wf.artifact_type)}</Badge>
                  <Badge variant={wf.mode === "SEQUENTIAL" ? "info" : "ai"}>
                    {wf.mode === "SEQUENTIAL" ? "Sequential" : "Parallel"}
                  </Badge>
                  {wf.active ? <StatusBadge status="ACTIVE" dot /> : <Badge variant="muted">Inactive</Badge>}
                </span>
              }
            >
              <div className="space-y-3">
                <ol className="space-y-1.5">
                  {(wf.steps ?? []).map((s) => (
                    <li key={s.order} className="flex items-center gap-2 text-sm">
                      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-secondary text-2xs font-semibold">
                        {s.order}
                      </span>
                      <span className="font-medium">
                        {s.approver_kind === "ROLE"
                          ? `${ROLE_LABEL[s.approver_role as Role] ?? s.approver_role}`
                          : "Named approver"}
                      </span>
                      {!s.required && <Badge variant="muted">Optional</Badge>}
                      <span className="text-2xs text-muted-foreground">· {s.timeout_hours}h timeout</span>
                    </li>
                  ))}
                  {(wf.steps ?? []).length === 0 && (
                    <li className="text-xs text-muted-foreground">No steps defined.</li>
                  )}
                </ol>
                <div className="flex items-center gap-2 border-t border-border pt-3">
                  <Switch
                    checked={wf.active}
                    onCheckedChange={() => toggle(wf)}
                    aria-label={wf.active ? "Deactivate workflow" : "Activate workflow"}
                  />
                  <span className="text-sm text-muted-foreground">
                    {wf.active ? "Active" : "Inactive"}
                  </span>
                </div>
              </div>
            </Panel>
          ))}
        </div>
      ) : (
        <EmptyState
          icon={GitBranch}
          title="No workflows yet"
          description="Create a workflow to route reviews or JDs through ordered approvers."
          action={<Button onClick={() => setCreateOpen(true)}>Create workflow</Button>}
        />
      )}

      <WorkflowDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}
