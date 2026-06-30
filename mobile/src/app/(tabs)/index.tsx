import * as React from "react";
import { Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { cyclesApi, feedbackApi, goalsApi, reviewsApi } from "@shared/api/endpoints";
import { useAuth } from "@/lib/auth";
import { Card, ErrorView, Icon, ICON, SectionTitle, type IconName } from "@/components/ui";

/** Dashboard — an employee/manager self-service cockpit composed from the real scoped
 *  endpoints (the same the web cockpit uses). Leads with what needs you today + an
 *  honest performance reading (a T-score, never a fake /5), then quick access to the
 *  everyday surfaces. Pull to refresh. */
export default function Dashboard() {
  const { me } = useAuth();
  const router = useRouter();
  const first = me?.display?.split(" ")[0] ?? "there";

  const goals = useQuery({ queryKey: ["goals", "mine"], queryFn: () => goalsApi.list({ page_size: 50 }) });
  const cycleId = goals.data?.results[0]?.cycle;
  const score = useQuery({
    queryKey: ["cycles", "myScore", cycleId],
    queryFn: () => cyclesApi.myScore(cycleId as string),
    enabled: Boolean(cycleId),
  });
  const reviews = useQuery({ queryKey: ["reviews", "mine"], queryFn: () => reviewsApi.list({ page_size: 10 }) });
  const requests = useQuery({ queryKey: ["feedback", "requests", "mine"], queryFn: feedbackApi.requestsMine });

  const refreshing = goals.isFetching || reviews.isFetching || requests.isFetching;
  const refetchAll = () => {
    void goals.refetch();
    void score.refetch();
    void reviews.refetch();
    void requests.refetch();
  };

  const s = score.data;
  const goalCount = goals.data?.results.length ?? 0;
  const reviewState = reviews.data?.results[0]?.state;
  const pendingReq = (requests.data ?? []).filter((r) => r.status === "PENDING").length;

  // "Needs you" — composed from REAL pending items only (never fabricated).
  const tasks: { id: string; label: string; sub: string; href: string; icon: IconName }[] = [];
  if (pendingReq > 0)
    tasks.push({ id: "fb", label: "Give 360 feedback", sub: `${pendingReq} request${pendingReq === 1 ? "" : "s"} awaiting you`, href: "/feedback", icon: "message-square" });
  if (reviewState === "FINALIZED")
    tasks.push({ id: "rv", label: "Read your review", sub: "Finalized this cycle", href: "/reviews", icon: "file-text" });
  if (goalCount > 0 && s && s.risk_status !== "ON_TRACK")
    tasks.push({ id: "gl", label: "Check your goals", sub: "Your performance needs attention", href: "/goals", icon: "target" });

  const statusLine =
    pendingReq > 0
      ? `${pendingReq} feedback request${pendingReq === 1 ? "" : "s"} waiting on you.`
      : s && s.risk_status !== "ON_TRACK"
        ? "Your performance needs attention this cycle."
        : "You're on track — here's your snapshot.";

  return (
    <ScrollView
      className="flex-1 bg-background"
      contentContainerClassName="p-5 gap-5"
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refetchAll} tintColor={ICON.primary} />}
    >
      {/* Hero */}
      <View>
        <Text className="text-2xl font-bold text-foreground">{greeting()}, {first}</Text>
        <Text className="mt-1 text-sm text-muted-foreground">{statusLine}</Text>
      </View>

      {goals.isError ? (
        <ErrorView error={goals.error} onRetry={refetchAll} />
      ) : (
        <>
          {/* Performance — the hero number, honest T-score + risk band */}
          <Card>
            <View className="flex-row items-center justify-between">
              <View>
                <SectionTitle>My performance</SectionTitle>
                <Text className={`mt-1.5 text-4xl font-bold ${s ? RISK_FG[s.risk_status] : "text-foreground"}`}>
                  {s ? Number(s.t_score).toFixed(0) : "—"}
                </Text>
                <Text className="mt-0.5 text-2xs text-muted-foreground">
                  {s ? `T-score · 50 = team average · ${RISK_LABEL[s.risk_status]}` : "Not yet scored this cycle"}
                </Text>
              </View>
              <View className="items-end">
                <Icon name="trending-up" size={22} color={s ? RISK_HEX[s.risk_status] : ICON.muted} />
                <Text className="mt-2 text-2xs text-muted-foreground">{goalCount} active goal{goalCount === 1 ? "" : "s"}</Text>
              </View>
            </View>
          </Card>

          {/* Needs you */}
          <View className="gap-2">
            <SectionTitle>Needs you</SectionTitle>
            {tasks.length > 0 ? (
              tasks.map((t) => (
                <Pressable key={t.id} onPress={() => router.push(t.href as never)}>
                  <Card className="flex-row items-center gap-3">
                    <View className="h-9 w-9 items-center justify-center rounded-full bg-primary/10">
                      <Icon name={t.icon} size={18} color={ICON.primary} />
                    </View>
                    <View className="flex-1">
                      <Text className="text-sm font-semibold text-foreground">{t.label}</Text>
                      <Text className="text-2xs text-muted-foreground">{t.sub}</Text>
                    </View>
                    <Icon name="chevron-right" size={18} />
                  </Card>
                </Pressable>
              ))
            ) : (
              <Card>
                <Text className="text-sm font-medium text-foreground">All caught up</Text>
                <Text className="mt-0.5 text-2xs text-muted-foreground">
                  No actions waiting. Record goal progress or recognize a teammate below.
                </Text>
              </Card>
            )}
          </View>

          {/* Quick access — surfaces the everyday features (no more "it's under More") */}
          <View className="gap-2">
            <SectionTitle>Quick access</SectionTitle>
            <View className="flex-row flex-wrap gap-3">
              {QUICK.map((q) => (
                <Pressable key={q.href} className="flex-1" style={{ minWidth: "45%" }} onPress={() => router.push(q.href as never)}>
                  <Card className="flex-row items-center gap-2.5">
                    <Icon name={q.icon} size={18} color={ICON.primary} />
                    <Text className="text-sm font-medium text-foreground">{q.label}</Text>
                  </Card>
                </Pressable>
              ))}
            </View>
          </View>
        </>
      )}
    </ScrollView>
  );
}

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

const QUICK: { label: string; href: string; icon: IconName }[] = [
  { label: "Goals", href: "/goals", icon: "target" },
  { label: "Reviews", href: "/reviews", icon: "file-text" },
  { label: "Check-ins", href: "/checkins", icon: "calendar" },
  { label: "Recognition", href: "/recognition", icon: "award" },
  { label: "Feedback", href: "/feedback", icon: "message-square" },
  { label: "Ask AI", href: "/chat", icon: "help-circle" },
];

const RISK_LABEL: Record<string, string> = { ON_TRACK: "On track", AT_RISK: "At risk", CRITICAL: "Critical" };
const RISK_FG: Record<string, string> = { ON_TRACK: "text-success", AT_RISK: "text-warning", CRITICAL: "text-danger" };
const RISK_HEX: Record<string, string> = { ON_TRACK: ICON.success, AT_RISK: "#d97706", CRITICAL: ICON.danger };
