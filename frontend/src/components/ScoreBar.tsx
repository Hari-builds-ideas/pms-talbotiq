import { cn } from "@/lib/utils";

/**
 * A plain 0–100 performance bar (v1). The point: a manager sees WHERE someone sits at a
 * glance — no statistics needed. Colored by the person's status band (green/amber/red);
 * the raw T-score is intentionally NOT the headline (see PERF_STATUS_LABEL usage — status
 * leads, the number is a small secondary detail). BUGS/V1_A: demote the T-score.
 */

/** risk_status → the plain words a non-expert reads first. */
export const PERF_STATUS_LABEL: Record<string, string> = {
  ON_TRACK: "On track",
  AT_RISK: "At risk",
  CRITICAL: "Needs attention",
};

const BAND: Record<string, string> = {
  ON_TRACK: "bg-success",
  AT_RISK: "bg-warning",
  CRITICAL: "bg-danger",
};

export function performanceLabel(status?: string | null): string {
  return (status && PERF_STATUS_LABEL[status]) || "Not yet scored";
}

/** A one-line tooltip that explains the number in plain English. */
export const T_SCORE_PLAIN = "A score where 50 is the team average — higher is better.";

export function ScoreBar({
  value,
  status,
  className,
}: {
  /** 0–100 position (the T-score). Omitted → an empty track ("not yet scored"). */
  value?: number | null;
  status?: string | null;
  className?: string;
}) {
  const pct = value == null ? null : Math.max(0, Math.min(100, value));
  const band = (status && BAND[status]) || "bg-muted-foreground";
  return (
    <div
      className={cn("h-2 w-full overflow-hidden rounded-full bg-secondary", className)}
      role="img"
      aria-label={
        pct == null ? "Not yet scored" : `${performanceLabel(status)} — ${Math.round(pct)} of 100`
      }
      title={T_SCORE_PLAIN}
    >
      {pct != null && (
        <div className={cn("h-full rounded-full transition-all", band)} style={{ width: `${pct}%` }} />
      )}
    </div>
  );
}
