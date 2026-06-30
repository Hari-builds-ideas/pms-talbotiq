import * as React from "react";
import { RefreshControl, ScrollView, Text, TextInput, View } from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { goalsApi } from "@shared/api/endpoints";
import { humanize } from "@shared/enums";
import type { Goal, Kpi } from "@shared/types";
import { Badge, Button, Card, EmptyView, ErrorView, Icon, Loading, SectionTitle } from "@/components/ui";

/** My goals & KPIs — read my active-cycle goals and record a KPI actual (the same
 *  audited endpoint the web uses). Scope is server-side: an employee sees only their own.
 *  Leads with a plain-language explainer so the weight/KPI/score model is legible. */
export default function Goals() {
  const q = useQuery({ queryKey: ["goals", "mine"], queryFn: () => goalsApi.list({ page_size: 100 }) });
  const goals = q.data?.results ?? [];

  if (q.isLoading) return <Loading label="Loading your goals…" />;
  if (q.isError) return <ErrorView error={q.error} onRetry={() => q.refetch()} />;

  return (
    <ScrollView
      className="flex-1 bg-background"
      contentContainerClassName="p-5 gap-4"
      refreshControl={<RefreshControl refreshing={q.isFetching} onRefresh={() => q.refetch()} tintColor="#0d5c3a" />}
    >
      {goals.length === 0 ? (
        <EmptyView title="No goals yet" description="Your goals for the active cycle will appear here once they're set." />
      ) : (
        <>
          <Card>
            <Text className="text-sm leading-relaxed text-muted-foreground">
              Each goal is <Text className="font-medium text-foreground">weighted</Text> for the cycle and has
              measurable <Text className="font-medium text-foreground">KPIs</Text> with targets. Record actuals
              as they happen — they roll up into your{" "}
              <Text className="font-medium text-foreground">performance score (a T-score)</Text>.
            </Text>
          </Card>
          {goals.map((g) => (
            <GoalCard key={g.id} goal={g} />
          ))}
        </>
      )}
    </ScrollView>
  );
}

function GoalCard({ goal }: { goal: Goal }) {
  const tone =
    goal.status === "ACHIEVED" ? "success" : goal.status === "MISSED" ? "danger" : goal.status === "ACTIVE" ? "primary" : "muted";
  return (
    <Card>
      {/* GOAL — title + its weight + status */}
      <View className="flex-row items-start justify-between gap-2">
        <Text className="flex-1 text-base font-semibold text-foreground">{goal.title}</Text>
        <View className="flex-row items-center gap-1.5">
          <Badge tone="muted">weight {String(goal.weight)}</Badge>
          <Badge tone={tone}>{humanize(goal.status)}</Badge>
        </View>
      </View>
      {goal.objective ? <Text className="mt-1 text-sm text-muted-foreground">{goal.objective}</Text> : null}
      {/* KPIs — belong to this goal */}
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

function Meta({ label, value, dim }: { label: string; value: string; dim?: boolean }) {
  return (
    <Text className="text-2xs text-muted-foreground">
      {label} <Text className={dim ? "italic" : "font-medium text-foreground"}>{value}</Text>
    </Text>
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

  const notRecorded = kpi.latest_actual == null || String(kpi.latest_actual) === "";
  const unit = kpi.unit ? ` ${kpi.unit}` : "";
  return (
    <View className="rounded-lg border border-border bg-muted/40 p-3">
      <Text className="text-sm font-medium text-foreground">{kpi.name}</Text>
      {/* weight · target · direction · actual */}
      <View className="mt-1 flex-row flex-wrap items-center gap-x-3 gap-y-0.5">
        <Meta label="weight" value={String(kpi.weight)} />
        <Meta label="target" value={`${String(kpi.target_value)}${unit}`} />
        <View className="flex-row items-center gap-1">
          <Icon name={kpi.direction === "INCREASING" ? "arrow-up" : "arrow-down"} size={12} />
          <Text className="text-2xs text-muted-foreground">{humanize(kpi.direction).toLowerCase()} is better</Text>
        </View>
        <Meta label="actual" value={notRecorded ? "not recorded yet" : `${String(kpi.latest_actual)}${unit}`} dim={notRecorded} />
      </View>

      {editing ? (
        <View className="mt-2 gap-2">
          <TextInput
            value={value}
            onChangeText={setValue}
            placeholder={`New actual${kpi.unit ? ` (${kpi.unit})` : ""}`}
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
          <Button title={notRecorded ? "Record actual" : "Update actual"} variant="outline" onPress={() => setEditing(true)} />
        </View>
      )}
    </View>
  );
}
