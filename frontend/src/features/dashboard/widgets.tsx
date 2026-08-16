import * as React from "react";
import { Link } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer } from "recharts";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/* ── Sparkline ─────────────────────────────────────────────────────────────
 * A tiny trend line for the KPI cards. Renders ONLY with a real ≥2-point series
 * (no fabricated trend); the caller passes already-real, already-scoped points. */
export function Sparkline({
  data,
  tone = "primary",
  height = 36,
}: {
  data: number[];
  tone?: "primary" | "success" | "danger";
  height?: number;
}) {
  if (!data || data.length < 2) return null;
  const stroke =
    tone === "danger" ? "hsl(var(--danger))" : tone === "success" ? "hsl(var(--success))" : "hsl(var(--primary))";
  const points = data.map((value, i) => ({ i, value }));
  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 4, right: 2, bottom: 2, left: 2 }}>
          <Line type="monotone" dataKey="value" stroke={stroke} strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ── DashboardKpiCard ──────────────────────────────────────────────────────
 * The mockup KPI tile: label → big value → optional honest delta + sparkline,
 * or a progress bar (e.g. review completion). No data → the trend simply omits
 * (never invented). */
export interface KpiDelta {
  dir: "up" | "down";
  text: string;
  /** When false, an "up" arrow is still drawn red (e.g. at-risk rising). */
  good?: boolean;
}

export function DashboardKpiCard({
  label,
  value,
  valueTone = "default",
  hint,
  delta,
  spark,
  sparkTone,
  progress,
  loading,
  to,
}: {
  label: string;
  value: React.ReactNode;
  valueTone?: "default" | "success" | "warning" | "danger";
  hint?: React.ReactNode;
  delta?: KpiDelta | null;
  spark?: number[];
  sparkTone?: "primary" | "success" | "danger";
  /** 0–100 → renders a progress bar instead of a sparkline. */
  progress?: number | null;
  loading?: boolean;
  to?: string;
}) {
  const valueColor =
    valueTone === "success"
      ? "text-success"
      : valueTone === "warning"
        ? "text-warning"
        : valueTone === "danger"
          ? "text-danger"
          : "text-foreground";

  const body = (
    <Card className={cn("flex h-full flex-col gap-3 p-5", to && "transition-shadow hover:border-primary/30 hover:shadow-md")}>
      <p className="text-sm font-medium text-muted-foreground">{label}</p>
      {loading ? (
        <Skeleton className="h-9 w-20" />
      ) : (
        <p className={cn("text-3xl font-bold tabular-nums tracking-tight", valueColor)}>{value}</p>
      )}

      {!loading && delta && (
        <p
          className={cn(
            "flex items-center gap-1 text-xs font-medium",
            (delta.good ?? delta.dir === "up") ? "text-success" : "text-danger",
          )}
        >
          {delta.dir === "up" ? <ArrowUpRight className="h-3.5 w-3.5" /> : <ArrowDownRight className="h-3.5 w-3.5" />}
          {delta.text}
        </p>
      )}

      {!loading && hint && <p className="text-xs text-muted-foreground">{hint}</p>}

      {!loading && typeof progress === "number" && (
        <div className="mt-auto h-2 w-full overflow-hidden rounded-full bg-secondary">
          <div className="h-full rounded-full bg-primary" style={{ width: `${Math.max(0, Math.min(100, progress))}%` }} />
        </div>
      )}

      {!loading && progress == null && spark && spark.length >= 2 && (
        <div className="mt-auto">
          <Sparkline data={spark} tone={sparkTone} />
        </div>
      )}
    </Card>
  );

  if (!to) return body;
  return (
    <Link to={to} aria-label={`${label} — open`} className="block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
      {body}
    </Link>
  );
}

/* ── ScoreDonut ────────────────────────────────────────────────────────────
 * Risk-band distribution donut. Bands are the REAL metric (risk_status), not a
 * 1–5 rating; the legend labels them as such. Center = real scored count. */
export interface DonutBand {
  key: string;
  label: string;
  value: number;
  color: string; // an hsl(var(--token)) string
}

export function ScoreDonut({ bands, centerValue, centerLabel }: { bands: DonutBand[]; centerValue: number; centerLabel: string }) {
  const total = bands.reduce((s, b) => s + b.value, 0);
  const data = bands.filter((b) => b.value > 0);
  return (
    <div className="flex items-center gap-5">
      <div className="relative h-[150px] w-[150px] shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="label" innerRadius={50} outerRadius={70} paddingAngle={2} stroke="none" isAnimationActive={false}>
              {data.map((b) => (
                <Cell key={b.key} fill={b.color} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-bold tabular-nums text-foreground">{centerValue}</span>
          <span className="text-2xs text-muted-foreground">{centerLabel}</span>
        </div>
      </div>
      <ul className="min-w-0 flex-1 space-y-2">
        {bands.map((b) => {
          const pct = total > 0 ? Math.round((b.value / total) * 100) : 0;
          return (
            <li key={b.key} className="flex items-center gap-2 text-sm">
              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: b.color }} />
              <span className="min-w-0 flex-1 truncate text-muted-foreground">{b.label}</span>
              <span className="font-semibold tabular-nums">{b.value}</span>
              <span className="w-10 text-right text-2xs text-muted-foreground tabular-nums">{pct}%</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/* ── DashboardSection ──────────────────────────────────────────────────────
 * A titled card section for the lower zone (table / radar / announcements). */
export function DashboardSection({
  title,
  icon: Icon,
  to,
  toLabel = "View all",
  children,
  className,
  scroll = false,
}: {
  title: string;
  icon?: LucideIcon;
  to?: string;
  toLabel?: string;
  children: React.ReactNode;
  className?: string;
  /** Cap the body height and scroll internally — for growable content (e.g. a
   *  large team table) so it never stretches the page. Mirrors Panel's `scroll`. */
  scroll?: boolean;
}) {
  return (
    <Card className={cn("flex flex-col", className)}>
      <div className="flex items-center justify-between gap-2 border-b border-border px-5 py-4">
        <div className="flex items-center gap-2">
          {Icon && <Icon className="h-4 w-4 text-muted-foreground" />}
          <h3 className="text-base font-semibold">{title}</h3>
        </div>
        {to && (
          <Link to={to} className="tap-target text-xs font-medium text-primary hover:underline">
            {toLabel}
          </Link>
        )}
      </div>
      <div className={cn("flex-1 p-5", scroll && "max-h-96 overflow-y-auto scrollbar-thin")}>
        {children}
      </div>
    </Card>
  );
}
