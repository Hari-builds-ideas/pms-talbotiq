import * as React from "react";
import { RefreshControl, ScrollView, Text, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { cyclesApi, feedbackApi, goalsApi, reviewsApi } from "@shared/api/endpoints";
import { humanize } from "@shared/enums";
import { useAuth } from "@/lib/auth";
import { Card, ErrorView } from "@/components/ui";

/** Dashboard — the employee/manager self-service cockpit: performance score, goals,
 *  review status and feedback asks, composed from the real scoped endpoints (the same
 *  the web cockpit uses). Pull to refresh. */
export default function Dashboard() {
  const { me } = useAuth();
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

  return (
    <ScrollView
      className="flex-1 bg-background"
      contentContainerClassName="p-5 gap-4"
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refetchAll} tintColor="#5B5BD6" />}
    >
      <View>
        <Text className="text-2xl font-bold text-foreground">Good to see you, {first}</Text>
        <Text className="mt-1 text-sm text-muted-foreground">
          {me?.role} · {me?.tenant_name ?? me?.tenant_slug}
        </Text>
      </View>

      {goals.isError ? (
        <ErrorView error={goals.error} onRetry={refetchAll} />
      ) : (
        <View className="gap-3">
          <View className="flex-row gap-3">
            <Stat
              label="Performance"
              value={s ? Number(s.t_score).toFixed(0) : "—"}
              hint={s ? RISK_LABEL[s.risk_status] : "Not yet scored"}
              tone={s ? RISK_TONE[s.risk_status] : "muted"}
            />
            <Stat label="My goals" value={String(goalCount)} hint="Active cycle" />
          </View>
          <View className="flex-row gap-3">
            <Stat label="Review" value={reviewState ? humanize(reviewState) : "—"} hint="This cycle" />
            <Stat
              label="Feedback asks"
              value={String(pendingReq)}
              hint="Awaiting you"
              tone={pendingReq > 0 ? "warning" : "muted"}
            />
          </View>
        </View>
      )}

      <Card>
        <Text className="text-sm text-muted-foreground">
          Pull to refresh. Use the tabs for Goals, Feedback and Career — and the More tab for
          check-ins, reviews, recognition and the AI assistant.
        </Text>
      </Card>
    </ScrollView>
  );
}

type Tone = "muted" | "success" | "warning" | "danger";
const RISK_LABEL: Record<string, string> = { ON_TRACK: "On track", AT_RISK: "At risk", CRITICAL: "Critical" };
const RISK_TONE: Record<string, Tone> = { ON_TRACK: "success", AT_RISK: "warning", CRITICAL: "danger" };
const TONE_FG: Record<Tone, string> = {
  muted: "text-foreground",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
};

function Stat({ label, value, hint, tone = "muted" }: { label: string; value: string; hint: string; tone?: Tone }) {
  return (
    <View className="flex-1 rounded-xl border border-border bg-card p-4">
      <Text className="text-xs font-medium text-muted-foreground">{label}</Text>
      <Text className={`mt-1 text-2xl font-bold ${TONE_FG[tone]}`}>{value}</Text>
      <Text className="mt-0.5 text-2xs text-muted-foreground">{hint}</Text>
    </View>
  );
}
