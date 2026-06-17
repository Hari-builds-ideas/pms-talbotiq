import { Check, Clock, MinusCircle, X } from "lucide-react";
import { Timeline, type TimelineItem } from "@/components/Stepper";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { PersonName } from "@/components/PersonName";
import { ROLE_LABEL, type Role } from "@/lib/enums";
import { formatDateTime, formatRelative, isOverdue } from "@/lib/format";
import type { ApprovalRoute, ApprovalStepInstance } from "@/lib/types";

const STEP_TONE: Record<string, TimelineItem["tone"]> = {
  APPROVED: "success",
  REJECTED: "danger",
  ESCALATED: "warning",
  SKIPPED: "muted",
  PENDING: "info",
};

function stepIcon(status: string) {
  switch (status) {
    case "APPROVED":
      return <Check />;
    case "REJECTED":
      return <X />;
    case "SKIPPED":
      return <MinusCircle />;
    default:
      return <Clock />;
  }
}

function approverLabel(step: ApprovalStepInstance) {
  if (step.approver) return <PersonName id={step.approver} name={step.approver_name} />;
  if (step.approver_role) return <span>{ROLE_LABEL[step.approver_role as Role]} (role)</span>;
  return <span>Unassigned</span>;
}

export function RouteTracker({ route }: { route: ApprovalRoute }) {
  const activeOrder =
    route.mode === "SEQUENTIAL"
      ? route.step_instances.find((s) => s.status === "PENDING")?.order
      : undefined;

  const items: TimelineItem[] = [...route.step_instances]
    .sort((a, b) => a.order - b.order)
    .map((step) => {
      const overdue = step.status === "PENDING" && isOverdue(step.due_at);
      const isActive = route.mode === "PARALLEL" ? step.status === "PENDING" : step.order === activeOrder;
      return {
        key: String(step.id ?? step.order),
        icon: stepIcon(step.status),
        tone: STEP_TONE[step.status] ?? "muted",
        title: (
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-muted-foreground">Step {step.order}</span>
            {approverLabel(step)}
            {isActive && step.status === "PENDING" && <Badge variant="info">Active</Badge>}
            {step.escalated && <Badge variant="warning">Escalated</Badge>}
            {overdue && <Badge variant="danger">Overdue</Badge>}
          </span>
        ),
        meta: (
          <span className="flex items-center gap-2">
            <StatusBadge status={step.status} />
            {step.status === "PENDING" && step.due_at && <span>due {formatRelative(step.due_at)}</span>}
            {step.decided_at && <span>{formatDateTime(step.decided_at)}</span>}
          </span>
        ),
        body: step.comment ? <p className="italic">“{step.comment}”</p> : undefined,
      };
    });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between rounded-lg border border-border bg-secondary/40 px-3 py-2.5">
        <div className="text-sm">
          <span className="font-medium">{route.mode === "SEQUENTIAL" ? "Sequential" : "Parallel"} route</span>
          <span className="ml-1 text-muted-foreground">· {route.artifact_type}</span>
        </div>
        <StatusBadge status={route.status} dot />
      </div>
      <Timeline items={items} />
    </div>
  );
}
