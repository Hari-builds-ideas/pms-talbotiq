import * as React from "react";
import { cn } from "@/lib/utils";

interface PageHeaderProps {
  title: React.ReactNode;
  description?: React.ReactNode;
  /** Primary action(s), right-aligned. */
  actions?: React.ReactNode;
  /** Optional eyebrow / breadcrumb element above the title. */
  eyebrow?: React.ReactNode;
  className?: string;
}

/** Consistent page header: eyebrow, title, description, primary action. */
export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
  className,
}: PageHeaderProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 pb-5 sm:flex-row sm:items-start sm:justify-between",
        className,
      )}
    >
      <div className="min-w-0 space-y-1">
        {eyebrow && (
          <div className="text-2xs font-semibold uppercase tracking-wide text-muted-foreground">
            {eyebrow}
          </div>
        )}
        <h1 className="truncate text-2xl font-semibold tracking-tight text-foreground">
          {title}
        </h1>
        {description && (
          <p className="max-w-2xl text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {actions && (
        <div className="flex shrink-0 items-center gap-2">{actions}</div>
      )}
    </div>
  );
}
