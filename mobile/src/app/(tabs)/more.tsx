import * as React from "react";
import { ActivityIndicator, Pressable, ScrollView, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { useAuth } from "@/lib/auth";
import { apiBaseUrl } from "@/lib/api";

/** More — the signed-in identity, quick links to the non-tab screens (check-ins,
 *  reviews, recognition, the AI assistant), and sign out. */
const LINKS: { href: string; label: string; icon: string }[] = [
  { href: "/checkins", label: "Weekly check-in", icon: "📝" },
  { href: "/reviews", label: "My reviews", icon: "📄" },
  { href: "/recognition", label: "Recognition", icon: "🏅" },
  { href: "/chat", label: "AI assistant", icon: "✨" },
];

const MANAGER_LINKS: { href: string; label: string; icon: string }[] = [
  { href: "/approvals", label: "Approvals inbox", icon: "✅" },
  { href: "/team-checkins", label: "Team check-ins", icon: "👥" },
];

export default function More() {
  const { me, features, logout, atLeast } = useAuth();
  const [busy, setBusy] = React.useState(false);
  const router = useRouter();
  const isManager = atLeast("MANAGER");

  return (
    <ScrollView className="flex-1 bg-background" contentContainerClassName="p-5 gap-4">
      <View className="rounded-xl border border-border bg-card p-4">
        <Text className="text-lg font-semibold text-foreground">{me?.display}</Text>
        <Text className="mt-0.5 text-sm text-muted-foreground">{me?.email}</Text>
        <View className="mt-3 flex-row flex-wrap gap-2">
          <Badge>{me?.role}</Badge>
          <Badge>{me?.tenant_name ?? me?.tenant_slug}</Badge>
          {me?.mfa_enabled ? <Badge>MFA on</Badge> : null}
        </View>
      </View>

      <View className="overflow-hidden rounded-xl border border-border bg-card">
        {LINKS.map((l, i) => (
          <Pressable
            key={l.href}
            onPress={() => router.push(l.href as never)}
            className={`flex-row items-center gap-3 px-4 py-3.5 ${i > 0 ? "border-t border-border" : ""}`}
          >
            <Text className="text-lg">{l.icon}</Text>
            <Text className="flex-1 text-base text-foreground">{l.label}</Text>
            <Text className="text-muted-foreground">›</Text>
          </Pressable>
        ))}
      </View>

      {isManager ? (
        <View>
          <Text className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">For your team</Text>
          <View className="overflow-hidden rounded-xl border border-border bg-card">
            {MANAGER_LINKS.map((l, i) => (
              <Pressable
                key={l.href}
                onPress={() => router.push(l.href as never)}
                className={`flex-row items-center gap-3 px-4 py-3.5 ${i > 0 ? "border-t border-border" : ""}`}
              >
                <Text className="text-lg">{l.icon}</Text>
                <Text className="flex-1 text-base text-foreground">{l.label}</Text>
                <Text className="text-muted-foreground">›</Text>
              </Pressable>
            ))}
          </View>
        </View>
      ) : null}

      <View className="rounded-xl border border-border bg-card p-4">
        <Text className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Plan features</Text>
        <Text className="mt-1 text-sm text-foreground">
          {features ? Object.entries(features).filter(([, on]) => on).map(([k]) => k).join(", ") || "Starter" : "—"}
        </Text>
      </View>

      <Pressable
        onPress={async () => { setBusy(true); await logout(); }}
        disabled={busy}
        className="items-center rounded-lg border border-danger/30 bg-danger-subtle py-3.5"
      >
        {busy ? <ActivityIndicator color="#EF4444" /> : <Text className="text-base font-semibold text-danger">Sign out</Text>}
      </Pressable>

      <Text className="text-center text-2xs text-muted-foreground">Backend: {apiBaseUrl}</Text>
    </ScrollView>
  );
}

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <View className="rounded-full bg-muted px-2.5 py-1">
      <Text className="text-xs font-medium text-muted-foreground">{children}</Text>
    </View>
  );
}
