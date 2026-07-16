import { cn } from "@/lib/utils";
import {
  PROGRESS_BAR_CLASS,
  PROGRESS_STATUS_LABEL,
  type ProgressStatus,
} from "@/lib/goalProgress";

/**
 * The v1 goal-progress bar — a colored, filled "% complete" bar (green on track,
 * amber behind, red at risk). This is the visual heart of the simplified Goals UI
 * and the replacement for the T-score number across the app. Pure presentation.
 */
export function ProgressBar({
  pct,
  status,
  className,
  size = "md",
}: {
  /** 0–100+ (capped for the fill); null renders an empty "not started" track. */
  pct: number | null;
  status: ProgressStatus | null;
  className?: string;
  size?: "sm" | "md";
}) {
  const width = pct == null ? 0 : Math.max(0, Math.min(100, pct));
  const band = status ? PROGRESS_BAR_CLASS[status] : "bg-muted-foreground/30";
  return (
    <div
      className={cn(
        "w-full overflow-hidden rounded-full bg-secondary",
        size === "sm" ? "h-1.5" : "h-2.5",
        className,
      )}
      role="img"
      aria-label={
        pct == null
          ? "Not started"
          : `${status ? PROGRESS_STATUS_LABEL[status] : ""} — ${Math.round(pct)}% complete`
      }
    >
      <div className={cn("h-full rounded-full transition-all", band)} style={{ width: `${width}%` }} />
    </div>
  );
}
