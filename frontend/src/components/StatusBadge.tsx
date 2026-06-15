import { Badge, type BadgeProps } from "@/components/ui/badge";
import { humanize } from "@/lib/enums";
import { cn } from "@/lib/utils";

type Variant = NonNullable<BadgeProps["variant"]>;

/**
 * The single source of truth for domain-status colour. Every status chip in the
 * app routes through here so DRAFT/PENDING/APPROVED etc. always look the same.
 * Convention (02_state_machines.md): terminal-positive = success; in-flight =
 * info/ai; negative = danger; neutral = muted.
 */
const STATUS_VARIANT: Record<string, Variant> = {
  // Reviews
  DRAFT: "muted",
  AI_DRAFTING: "ai",
  PENDING_HUMAN_REVIEW: "warning",
  EDITING: "info",
  APPROVED: "success",
  REJECTED: "danger",
  FINALIZED: "success",
  // Generic lifecycle
  ACTIVE: "success",
  CLOSED: "muted",
  ACHIEVED: "success",
  MISSED: "danger",
  ARCHIVED: "muted",
  // Cycles / tenant
  SUSPENDED: "warning",
  CANCELLED: "danger",
  // Approval routes + steps
  IN_PROGRESS: "info",
  ESCALATED: "warning",
  SKIPPED: "muted",
  PENDING: "warning",
  // JD
  IN_REVIEW: "info",
  PUBLISHED: "success",
  // Positions
  OPEN: "info",
  FILLED: "success",
  // Feedback
  COLLECTING: "info",
  HRBP_HOLD: "warning",
  RELEASED: "success",
  SUBMITTED: "success",
  DECLINED: "muted",
  // Succession coverage
  GREEN: "success",
  AMBER: "warning",
  RED: "danger",
  // Risk
  ON_TRACK: "success",
  AT_RISK: "warning",
  CRITICAL: "danger",
  // Readiness
  READY_NOW: "success",
  READY_SOON: "info",
  DEVELOPING: "warning",
  NOT_READY: "danger",
  // Bands / knowledge risk / criticality
  HIGH: "danger",
  MEDIUM: "warning",
  LOW: "muted",
  // Roadmap progress
  NOT_STARTED: "muted",
  DONE: "success",
  // Requests
  FULFILLED: "success",
  // Nudge levels
  STANDARD: "warning",
  SUPPRESSED: "muted",
};

export interface StatusBadgeProps {
  status?: string | null;
  className?: string;
  /** Override the auto-derived variant. */
  variant?: Variant;
  /** Show a small leading dot. */
  dot?: boolean;
}

export function StatusBadge({ status, className, variant, dot }: StatusBadgeProps) {
  if (!status) return <span className="text-muted-foreground">—</span>;
  const resolved = variant ?? STATUS_VARIANT[status] ?? "secondary";
  return (
    <Badge variant={resolved} className={cn("font-medium", className)}>
      {dot && (
        <span
          className={cn("h-1.5 w-1.5 rounded-full bg-current opacity-80")}
          aria-hidden
        />
      )}
      {humanize(status)}
    </Badge>
  );
}

export { STATUS_VARIANT };
