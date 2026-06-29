import * as React from "react";
import { RefreshControl, ScrollView, Text, TextInput, View } from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { goalsApi } from "@shared/api/endpoints";
import { humanize } from "@shared/enums";
import type { Goal, Kpi } from "@shared/types";
import { Badge, Button, Card, EmptyView, ErrorView, Loading, SectionTitle } from "@/components/ui";

/** My goals & KPIs — read my active-cycle goals and record a KPI actual (the same
 *  audited endpoint the web uses). Scope is server-side: an employee sees only their own. */
export default function Goals() {
  const q = useQuery({ queryKey: ["goals", "mine"], queryFn: () => goalsApi.list({ page_size: 100 }) });
  const goals = q.data?.results ?? [];

  if (q.isLoading) return <Loading label="Loading your goals…" />;
  if (q.isError) return <ErrorView error={q.error} onRetry={() => q.refetch()} />;

  return (
    <ScrollView
      className="flex-1 bg-background"
      contentContainerClassName="p-5 gap-4"
      refreshControl={<RefreshControl refreshing={q.isFetching} onRefresh={() => q.refetch()} tintColor="#5B5BD6" />}
    >
      {goals.length === 0 ? (
        <EmptyView title="No goals yet" description="Your goals for the active cycle will appear here." />
      ) : (
        goals.map((g) => <GoalCard key={g.id} goal={g} />)
      )}
    </ScrollView>
  );
}

function GoalCard({ goal }: { goal: Goal }) {
  const tone =
    goal.status === "ACHIEVED" ? "success" : goal.status === "MISSED" ? "danger" : goal.status === "ACTIVE" ? "primary" : "muted";
  return (
    <Card>
      <View className="flex-row items-start justify-between gap-2">
        <Text className="flex-1 text-base font-semibold text-foreground">{goal.title}</Text>
        <Badge tone={tone}>{humanize(goal.status)}</Badge>
      </View>
      {goal.objective ? <Text className="mt-1 text-sm text-muted-foreground">{goal.objective}</Text> : null}
      <View className="mt-3 gap-2">
        <SectionTitle>KPIs</SectionTitle>
        {goal.kpis.length === 0 ? (
          <Text className="text-sm text-muted-foreground">No KPIs on this goal.</Text>
        ) : (
          goal.kpis.map((k) => <KpiRow key={k.id} kpi={k} />)
        )}
      </View>
    </Card>
  );
}

function KpiRow({ kpi }: { kpi: Kpi }) {
  const qc = useQueryClient();
  const [editing, setEditing] = React.useState(false);
  const [value, setValue] = React.useState("");
  const m = useMutation({
    mutationFn: (v: string) => goalsApi.recordActual(kpi.id, v),
    onSuccess: () => {
      setEditing(false);
      setValue("");
      void qc.invalidateQueries({ queryKey: ["goals"] });
      void qc.invalidateQueries({ queryKey: ["cycles"] });
    },
  });

  const arrow = kpi.direction === "INCREASING" ? "↑" : "↓";
  const actual = kpi.latest_actual != null ? String(kpi.latest_actual) : "—";
  return (
    <View className="rounded-lg border border-border bg-muted/40 p-3">
      <View className="flex-row items-center justify-between gap-2">
        <Text className="flex-1 text-sm font-medium text-foreground">{kpi.name}</Text>
        <Text className="text-2xs text-muted-foreground">
          {arrow} target {String(kpi.target_value)} {kpi.unit}
        </Text>
      </View>
      <Text className="mt-1 text-2xs text-muted-foreground">Latest actual: {actual} {kpi.unit}</Text>

      {editing ? (
        <View className="mt-2 gap-2">
          <TextInput
            value={value}
            onChangeText={setValue}
            placeholder={`New actual (${kpi.unit})`}
            keyboardType="numeric"
            className="rounded-md border border-border bg-card px-3 py-2 text-sm text-foreground"
          />
          {m.isError ? <Text className="text-2xs text-danger">Could not save — check the value.</Text> : null}
          <View className="flex-row gap-2">
            <Button title="Save" onPress={() => value.trim() && m.mutate(value.trim())} loading={m.isPending} className="flex-1" />
            <Button title="Cancel" variant="outline" onPress={() => setEditing(false)} className="flex-1" />
          </View>
        </View>
      ) : (
        <View className="mt-2 self-start">
          <Button title="Record actual" variant="outline" onPress={() => setEditing(true)} />
        </View>
      )}
    </View>
  );
}
