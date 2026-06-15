import * as React from "react";
import type { LucideIcon } from "lucide-react";
import { Inbox } from "lucide-react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  /** Explain WHY there's no data and WHAT can be done (V0 brief rule). */
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  /** Compact variant for inline/table empties. */
  compact?: boolean;
}

/** Professional, actionable empty state — no playful illustrations. */
export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  className,
  compact,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-card/40 text-center",
        compact ? "gap-2 px-6 py-10" : "gap-3 px-6 py-16",
        className,
      )}
    >
      <div className="flex h-11 w-11 items-center justify-center rounded-full bg-secondary text-muted-foreground">
        <Icon className="h-5 w-5" aria-hidden />
      </div>
      <div className="space-y-1">
        <p className="text-md font-semibold text-foreground">{title}</p>
        {description && (
          <p className="mx-auto max-w-md text-sm text-muted-foreground">
            {description}
          </p>
        )}
      </div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}
