import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useIsDesktop } from "@/lib/hooks/useIsDesktop";

export interface TrendPoint {
  label: string;
  value: number;
}

/**
 * A compact area trend chart (recharts) in the indigo chart-1 token. Pure
 * presentation — the caller passes real, already-scoped data points. Used for the
 * individual performance trend; `seriesName` labels the series in the tooltip
 * (v1 plots "Progress %", the v2 T-score view plots "T-score").
 */
export function TrendChart({
  data,
  height = 220,
  seriesName = "T-score",
}: {
  data: TrendPoint[];
  height?: number;
  seriesName?: string;
}) {
  const isDesktop = useIsDesktop();
  // Floor the height. A caller passing a small number (or a flex parent
  // collapsing) turns a chart into an unreadable 40px sliver; 180px is the least
  // that still shows a trend.
  const h = Math.max(height, 180);
  return (
    <div style={{ width: "100%", height: h }} className="text-2xs">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
          <defs>
            <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="hsl(var(--chart-1))" stopOpacity={0.28} />
              <stop offset="100%" stopColor="hsl(var(--chart-1))" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fontSize: isDesktop ? 11 : 10, fill: "hsl(var(--muted-foreground))" }}
            tickLine={false}
            axisLine={{ stroke: "hsl(var(--border))" }}
            // A phone gives this chart ~300px. Rendering every label there
            // overlaps them into a grey smear, so below md keep the first and
            // last and let recharts drop the rest, with a wide minimum gap.
            interval={isDesktop ? "preserveEnd" : "preserveStartEnd"}
            minTickGap={isDesktop ? 8 : 32}
          />
          <YAxis
            tick={{ fontSize: isDesktop ? 11 : 10, fill: "hsl(var(--muted-foreground))" }}
            tickLine={false}
            axisLine={false}
            // Narrower gutter and fewer gridlines on a phone: the axis was
            // spending 36 of ~300px on labels.
            width={isDesktop ? 36 : 28}
            tickCount={isDesktop ? undefined : 4}
          />
          <Tooltip
            cursor={{ stroke: "hsl(var(--border))" }}
            contentStyle={{
              borderRadius: 12,
              border: "1px solid hsl(var(--border))",
              background: "hsl(var(--popover))",
              fontSize: 12,
              boxShadow: "0 4px 12px -2px rgb(15 23 42 / 0.08)",
            }}
            labelStyle={{ color: "hsl(var(--muted-foreground))" }}
          />
          <Area
            type="monotone"
            dataKey="value"
            name={seriesName}
            stroke="hsl(var(--chart-1))"
            strokeWidth={2}
            fill="url(#trendFill)"
            dot={{ r: 3, fill: "hsl(var(--chart-1))", strokeWidth: 0 }}
            activeDot={{ r: 4 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
