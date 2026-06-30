import { cn } from "@/lib/utils";

/**
 * Attainment gauge for a KPI (BUILD_5 5.2): latest actual vs target, direction-
 * aware. INCREASING → actual/target; DECREASING (lower is better) → target/actual.
 * Capped at 100% for the bar; the exact % is shown. No actual yet → a muted
 * "not recorded" state (never a misleading 0%).
 */
export function AttainmentBar({
  actual,
  target,
  direction,
  className,
}: {
  actual?: string | number | null;
  target: string | number;
  direction: "INCREASING" | "DECREASING";
  className?: string;
}) {
  const t = Number(target);
  if (actual === null || actual === undefined || actual === "") {
    return (
      <div className={cn("flex items-center gap-2 text-2xs text-muted-foreground", className)}>
        <div className="h-1.5 flex-1 rounded-full bg-secondary" />
        <span>not recorded yet</span>
      </div>
    );
  }
  const a = Number(actual);
  const ratio = direction === "INCREASING" ? (t ? a / t : 0) : a ? t / a : 0;
  const pctExact = Math.max(0, ratio * 100);
  const pctBar = Math.min(100, pctExact);
  const fill = pctExact >= 100 ? "bg-success" : pctExact >= 70 ? "bg-info" : "bg-warning";
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary">
        <div className={cn("h-full rounded-full", fill)} style={{ width: `${pctBar}%` }} />
      </div>
      <span className="w-10 shrink-0 text-right text-2xs tabular-nums text-muted-foreground">
        {Math.round(pctExact)}%
      </span>
    </div>
  );
}
