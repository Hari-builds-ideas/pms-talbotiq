import * as React from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface PanelProps {
  title: string;
  icon?: LucideIcon;
  /** Right-aligned header element (e.g. a count badge or filter). */
  aside?: React.ReactNode;
  /** A "view all" style link rendered in the header. */
  to?: string;
  toLabel?: string;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  /** Cap the body at a fixed height and scroll internally — for growable lists
   *  (approval inbox, nudges, stale goals) so a long list scrolls WITHIN the card
   *  instead of stretching the whole page. No data is hidden; it's reachable by
   *  scrolling (and the header's "View all" links to the full screen). */
  scroll?: boolean;
}

/** A titled content panel — the workhorse container for dashboard + list views. */
export function Panel({
  title,
  icon: Icon,
  aside,
  to,
  toLabel = "View all",
  children,
  className,
  bodyClassName,
  scroll = false,
}: PanelProps) {
  return (
    <Card className={cn("flex flex-col", className)}>
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          {Icon && <Icon className="h-4 w-4 text-muted-foreground" />}
          <h3 className="text-sm font-semibold">{title}</h3>
          {aside}
        </div>
        {to && (
          <Link
            to={to}
            className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
          >
            {toLabel}
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        )}
      </div>
      <div
        className={cn(
          "flex-1 p-4",
          scroll && "max-h-72 overflow-y-auto scrollbar-thin",
          bodyClassName,
        )}
      >
        {children}
      </div>
    </Card>
  );
}
