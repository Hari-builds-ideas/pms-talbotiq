import * as React from "react";
import { RefreshControl, ScrollView, Text, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { careerApi } from "@shared/api/endpoints";
import type { DevelopmentRoadmap } from "@shared/types";
import { Badge, Card, EmptyView, ErrorView, Loading, SectionTitle } from "@/components/ui";

/** My development roadmap — read-only: the target role, the deterministic skill gap, and
 *  the ordered tiers (each: what to focus on, why, and what 'done' looks like). Advisory. */
export default function Career() {
  const q = useQuery({ queryKey: ["career", "roadmap", "mine"], queryFn: () => careerApi.roadmap() });
  const roadmap: DevelopmentRoadmap | undefined =
    q.data?.results.find((r) => r.status === "ACTIVE") ?? q.data?.results[0];

  if (q.isLoading) return <Loading label="Loading your roadmap…" />;
  if (q.isError) return <ErrorView error={q.error} onRetry={() => q.refetch()} />;

  return (
    <ScrollView
      className="flex-1 bg-background"
      contentContainerClassName="p-5 gap-4"
      refreshControl={<RefreshControl refreshing={q.isFetching} onRefresh={() => q.refetch()} tintColor="#0d5c3a" />}
    >
      {!roadmap ? (
        <EmptyView
          title="No roadmap yet"
          description="Your manager can set up a development roadmap toward a target role."
        />
      ) : (
        <>
          <Card>
            <SectionTitle>Target role</SectionTitle>
            <Text className="mt-1 text-lg font-semibold text-foreground">
              {roadmap.target_jd_title ?? roadmap.target_position_title ?? "—"}
            </Text>
            <View className="mt-2 flex-row flex-wrap gap-2">
              <Badge tone={roadmap.source === "AI" ? "ai" : "muted"}>
                {roadmap.source === "AI" ? "AI-enriched" : "Deterministic"}
              </Badge>
              {roadmap.advisory ? <Badge>Advisory</Badge> : null}
            </View>
            {roadmap.skill_gap ? (
              <Text className="mt-3 text-sm text-muted-foreground">
                {roadmap.skill_gap.current_performance_band ?? "—"} → {roadmap.skill_gap.required_performance_band ?? "—"}
                {typeof roadmap.skill_gap.performance_band_gap === "number"
                  ? ` (gap ${roadmap.skill_gap.performance_band_gap})`
                  : ""}
              </Text>
            ) : null}
          </Card>

          <SectionTitle>Development tiers</SectionTitle>
          {roadmap.tiers.length === 0 ? (
            <Text className="text-sm text-muted-foreground">No tiers on this roadmap.</Text>
          ) : (
            roadmap.tiers
              .slice()
              .sort((a, b) => a.index - b.index)
              .map((t) => (
                <Card key={t.index}>
                  <View className="flex-row items-center gap-2">
                    <View className="h-6 w-6 items-center justify-center rounded-full bg-primary/10">
                      <Text className="text-xs font-bold text-primary">{t.index + 1}</Text>
                    </View>
                    <Text className="flex-1 text-base font-semibold text-foreground">{t.title}</Text>
                  </View>
                  {t.detail ? <Text className="mt-2 text-sm text-foreground">{t.detail}</Text> : null}
                  {t.basis ? <Text className="mt-1 text-2xs text-muted-foreground">Why: {t.basis}</Text> : null}
                </Card>
              ))
          )}
        </>
      )}
    </ScrollView>
  );
}
