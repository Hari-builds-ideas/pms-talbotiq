import * as React from "react";
import { Link } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: React.ReactNode;
  icon?: LucideIcon;
  hint?: React.ReactNode;
  /** Accent the value/icon for emphasis (e.g. risk counts). */
  tone?: "default" | "success" | "warning" | "danger" | "info" | "ai" | "premium";
  loading?: boolean;
  className?: string;
  /** When set, the whole card becomes a link to the action (the "needs-you"
   *  command-center pattern — each metric navigates straight to where you act). */
  to?: string;
}

const TONE: Record<NonNullable<StatCardProps["tone"]>, { icon: string; value: string }> = {
  default: { icon: "bg-secondary text-muted-foreground", value: "text-foreground" },
  success: { icon: "bg-success-subtle text-success", value: "text-foreground" },
  warning: { icon: "bg-warning-subtle text-warning", value: "text-foreground" },
  danger: { icon: "bg-danger-subtle text-danger", value: "text-foreground" },
  info: { icon: "bg-info-subtle text-info", value: "text-foreground" },
  ai: { icon: "bg-ai-subtle text-ai", value: "text-foreground" },
  premium: { icon: "bg-premium-subtle text-premium", value: "text-foreground" },
};

export function StatCard({
  label,
  value,
  icon: Icon,
  hint,
  tone = "default",
  loading,
  className,
  to,
}: StatCardProps) {
  const t = TONE[tone];
  const card = (
    <Card
      className={cn(
        "p-4",
        to && "transition-shadow hover:border-ring/40 hover:shadow-md",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          {loading ? (
            <Skeleton className="h-7 w-12" />
          ) : (
            <p className={cn("text-2xl font-semibold tabular-nums", t.value)}>{value}</p>
          )}
          {hint && !loading && (
            <p className="truncate text-2xs text-muted-foreground">{hint}</p>
          )}
        </div>
        {Icon && (
          <div className={cn("flex h-9 w-9 items-center justify-center rounded-lg", t.icon)}>
            <Icon className="h-4 w-4" />
          </div>
        )}
      </div>
    </Card>
  );
  if (!to) return card;
  return (
    <Link
      to={to}
      aria-label={`${label} — open`}
      className="block rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {card}
    </Link>
  );
}
