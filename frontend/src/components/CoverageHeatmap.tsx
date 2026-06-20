import { cn } from "@/lib/utils";
import type { CriticalRoleSummary } from "@/lib/types";

// Succession coverage at a glance (BUILD_5 5.4b): a proportional RED/AMBER/GREEN
// band + counts across the tenant's critical roles, so the gaps that need a plan
// read instantly above the per-role grid.
const SEG = {
  RED: { label: "Gap", bar: "bg-danger", text: "text-danger" },
  AMBER: { label: "At risk", bar: "bg-warning", text: "text-warning" },
  GREEN: { label: "Covered", bar: "bg-success", text: "text-success" },
} as const;

type Cov = keyof typeof SEG;
const ORDER: Cov[] = ["RED", "AMBER", "GREEN"];

export function CoverageHeatmap({ roles }: { roles: CriticalRoleSummary[] }) {
  const total = roles.length;
  if (!total) return null;
  const counts: Record<Cov, number> = { RED: 0, AMBER: 0, GREEN: 0 };
  for (const r of roles) {
    if (r.coverage_status in counts) counts[r.coverage_status as Cov] += 1;
  }
  return (
    <div className="rounded-lg border border-border p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">
          Coverage across {total} critical role{total === 1 ? "" : "s"}
        </span>
        <span className="text-2xs text-muted-foreground">RED gaps are the priority</span>
      </div>
      <div className="mt-2 flex h-2.5 w-full overflow-hidden rounded-full bg-secondary">
        {ORDER.map((k) =>
          counts[k] > 0 ? (
            <div
              key={k}
              className={cn("h-full", SEG[k].bar)}
              style={{ width: `${(counts[k] / total) * 100}%` }}
              title={`${counts[k]} ${SEG[k].label}`}
            />
          ) : null,
        )}
      </div>
      <div className="mt-2 flex flex-wrap gap-4 text-2xs">
        {ORDER.map((k) => (
          <span key={k} className="flex items-center gap-1.5">
            <span className={cn("h-2 w-2 rounded-full", SEG[k].bar)} />
            <span className="text-muted-foreground">{SEG[k].label}</span>
            <span className={cn("font-semibold tabular-nums", SEG[k].text)}>{counts[k]}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
