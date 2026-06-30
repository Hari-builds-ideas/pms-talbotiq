import * as React from "react";
import { ActivityIndicator, Pressable, Text, View } from "react-native";
import { Feather } from "@expo/vector-icons";
import { mapApiError } from "@shared/errors";

/** Shared mobile UI primitives — the SAME brand tokens as web, as NativeWind classes.
 *  Keeps the screens DRY + consistent (card surfaces, loading / error / empty states,
 *  pills, buttons). Read-only presentational helpers; no data logic here. */

/** A real icon (Feather — the lucide-equivalent the web uses) instead of emoji.
 *  Defaults to the muted slate token; pass a brand hex for emphasis. */
export type IconName = React.ComponentProps<typeof Feather>["name"];
export function Icon({ name, size = 18, color = "#64748b" }: { name: IconName; size?: number; color?: string }) {
  return <Feather name={name} size={size} color={color} />;
}
export const ICON = { primary: "#0d5c3a", muted: "#64748b", danger: "#dc2626", success: "#16a34a", white: "#FFFFFF" } as const;

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <View className={`rounded-xl border border-border bg-card p-4 ${className}`}>{children}</View>;
}

export function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <Text className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{children}</Text>
  );
}

export function Badge({ children, tone = "muted" }: { children: React.ReactNode; tone?: BadgeTone }) {
  const cls = BADGE_TONE[tone];
  return (
    <View className={`self-start rounded-full px-2.5 py-1 ${cls.bg}`}>
      <Text className={`text-xs font-medium ${cls.fg}`}>{children}</Text>
    </View>
  );
}

type BadgeTone = "muted" | "primary" | "success" | "warning" | "danger" | "ai";
const BADGE_TONE: Record<BadgeTone, { bg: string; fg: string }> = {
  muted: { bg: "bg-muted", fg: "text-muted-foreground" },
  primary: { bg: "bg-primary/10", fg: "text-primary" },
  success: { bg: "bg-success-subtle", fg: "text-success" },
  warning: { bg: "bg-warning-subtle", fg: "text-warning" },
  danger: { bg: "bg-danger-subtle", fg: "text-danger" },
  ai: { bg: "bg-ai/10", fg: "text-ai" },
};

export function Loading({ label }: { label?: string }) {
  return (
    <View className="flex-1 items-center justify-center gap-3 p-8">
      <ActivityIndicator color="#0d5c3a" />
      {label ? <Text className="text-sm text-muted-foreground">{label}</Text> : null}
    </View>
  );
}

export function ErrorView({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const mapped = mapApiError(error);
  return (
    <View className="items-center gap-3 p-8">
      <Text className="text-center text-sm text-danger">{mapped.message}</Text>
      {onRetry ? (
        <Button title="Retry" variant="outline" onPress={onRetry} />
      ) : null}
    </View>
  );
}

export function EmptyView({ title, description }: { title: string; description?: string }) {
  return (
    <View className="items-center gap-1 p-8">
      <Text className="text-center text-base font-semibold text-foreground">{title}</Text>
      {description ? <Text className="text-center text-sm text-muted-foreground">{description}</Text> : null}
    </View>
  );
}

type ButtonVariant = "primary" | "outline" | "danger";
export function Button({
  title,
  onPress,
  variant = "primary",
  loading = false,
  disabled = false,
  className = "",
}: {
  title: string;
  onPress: () => void;
  variant?: ButtonVariant;
  loading?: boolean;
  disabled?: boolean;
  className?: string;
}) {
  const v = BUTTON_VARIANT[variant];
  const off = disabled || loading;
  return (
    <Pressable
      onPress={onPress}
      disabled={off}
      className={`items-center justify-center rounded-lg py-3 ${v.bg} ${off ? "opacity-50" : ""} ${className}`}
    >
      {loading ? (
        <ActivityIndicator color={v.spinner} />
      ) : (
        <Text className={`text-base font-semibold ${v.fg}`}>{title}</Text>
      )}
    </Pressable>
  );
}

const BUTTON_VARIANT: Record<ButtonVariant, { bg: string; fg: string; spinner: string }> = {
  primary: { bg: "bg-primary", fg: "text-primary-foreground", spinner: "#FFFFFF" },
  outline: { bg: "border border-border bg-card", fg: "text-foreground", spinner: "#0d5c3a" },
  danger: { bg: "border border-danger/30 bg-danger-subtle", fg: "text-danger", spinner: "#dc2626" },
};
