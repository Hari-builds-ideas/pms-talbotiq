import { cn } from "@/lib/utils";

/**
 * Live KPI-weight indicator (BUILD_5 5.2). The KPI weights of a goal must sum to
 * EXACTLY 100.00 (server-enforced); this shows that sum in real time as a bar
 * that reads green when balanced, amber under, red over — so the editor never
 * has to do the arithmetic in their head.
 */
export function WeightBar({ total, className }: { total: number; className?: string }) {
  const pct = Math.min(100, Math.max(0, total));
  const state = total === 100 ? "ok" : total > 100 ? "over" : "under";
  const fill =
    state === "ok" ? "bg-success" : state === "over" ? "bg-danger" : "bg-warning";
  const note =
    state === "ok"
      ? "Balanced"
      : state === "over"
        ? `Over by ${(total - 100).toFixed(2)}`
        : `${(100 - total).toFixed(2)} to allocate`;
  return (
    <div className={className}>
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium">KPI weight</span>
        <span className="tabular-nums text-muted-foreground">
          {total.toFixed(2)} / 100 · <span className={cn(state === "ok" ? "text-success" : state === "over" ? "text-danger" : "text-warning")}>{note}</span>
        </span>
      </div>
      <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-secondary">
        <div
          className={cn("h-full rounded-full transition-[width,background-color]", fill)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
