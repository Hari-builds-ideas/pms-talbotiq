import * as React from "react";
import { Pressable, RefreshControl, ScrollView, Text, TextInput, View } from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { checkinsApi } from "@shared/api/endpoints";
import type { CheckIn } from "@shared/types";
import { Badge, Button, Card, ErrorView, Loading, SectionTitle } from "@/components/ui";

/** Weekly check-in — the employee loop: this week's mood + wins + blockers + learning +
 *  priorities (edit in place), plus earlier weeks with the manager's response. Same
 *  upsert endpoint the web uses; scope is server-side (you see only your own). */
const MOODS = [
  { v: 1, label: "Tough" },
  { v: 2, label: "Low" },
  { v: 3, label: "Okay" },
  { v: 4, label: "Good" },
  { v: 5, label: "Great" },
];
const moodLabel = (v: number) => MOODS.find((m) => m.v === v)?.label ?? "—";

function mondayOf(d = new Date()): string {
  const diff = (d.getDay() + 6) % 7; // days since Monday
  const monday = new Date(d);
  monday.setDate(d.getDate() - diff);
  return monday.toISOString().slice(0, 10);
}

export default function Checkins() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["checkins", "mine"], queryFn: checkinsApi.mine });
  const week = mondayOf();
  const mine = q.data ?? [];
  const thisWeek = mine.find((c) => c.week_of === week);
  const past = mine.filter((c) => c.week_of !== week);

  const [mood, setMood] = React.useState(0);
  const [wins, setWins] = React.useState("");
  const [blockers, setBlockers] = React.useState("");
  const [learning, setLearning] = React.useState("");
  const [priorities, setPriorities] = React.useState("");

  React.useEffect(() => {
    if (thisWeek) {
      setMood(thisWeek.mood);
      setWins(thisWeek.wins);
      setBlockers(thisWeek.blockers);
      setLearning(thisWeek.learning);
      setPriorities(thisWeek.priorities.map((p) => p.text).join("\n"));
    }
  }, [thisWeek]);

  const save = useMutation({
    mutationFn: () =>
      checkinsApi.upsert({
        week_of: week,
        mood,
        wins,
        blockers,
        learning,
        priorities: priorities
          .split("\n")
          .map((x) => x.trim())
          .filter(Boolean)
          .map((text) => ({ text, status: "ACTIVE" as const })),
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["checkins"] }),
  });

  if (q.isLoading) return <Loading label="Loading your check-ins…" />;
  if (q.isError) return <ErrorView error={q.error} onRetry={() => q.refetch()} />;

  return (
    <ScrollView
      className="flex-1 bg-background"
      contentContainerClassName="p-5 gap-4"
      keyboardShouldPersistTaps="handled"
      refreshControl={<RefreshControl refreshing={q.isFetching} onRefresh={() => q.refetch()} tintColor="#0d5c3a" />}
    >
      <Card>
        <Text className="text-base font-semibold text-foreground">This week</Text>
        <Text className="text-2xs text-muted-foreground">Week of {week} · a quick pulse your manager sees and can respond to.</Text>

        <Text className="mt-3 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">How was your week?</Text>
        <View className="mt-1.5 flex-row gap-2">
          {MOODS.map((x) => {
            const on = mood === x.v;
            return (
              <Pressable
                key={x.v}
                onPress={() => setMood(x.v)}
                className={`flex-1 items-center rounded-lg border py-2 ${on ? "border-primary bg-primary/10" : "border-border bg-card"}`}
              >
                <Text className={`text-base font-bold ${on ? "text-primary" : "text-foreground"}`}>{x.v}</Text>
                <Text className={`text-2xs ${on ? "text-primary" : "text-muted-foreground"}`}>{x.label}</Text>
              </Pressable>
            );
          })}
        </View>

        <Field label="Wins" value={wins} onChange={setWins} placeholder="What went well?" />
        <Field label="Blockers" value={blockers} onChange={setBlockers} placeholder="What's in your way?" />
        <Field label="Learning" value={learning} onChange={setLearning} placeholder="Anything you learned?" />
        <Field label="Priorities (one per line)" value={priorities} onChange={setPriorities} placeholder="Top things for next week" />
        <View className="mt-3">
          <Button
            title={thisWeek ? "Update check-in" : "Share check-in"}
            onPress={() => save.mutate()}
            loading={save.isPending}
            disabled={!mood}
          />
        </View>
      </Card>

      {past.length > 0 ? (
        <>
          <SectionTitle>Earlier weeks</SectionTitle>
          {past.map((c) => <PastCard key={c.id} c={c} />)}
        </>
      ) : null}
    </ScrollView>
  );
}

function Field({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (s: string) => void; placeholder: string }) {
  return (
    <View className="mt-3">
      <Text className="text-2xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        multiline
        className="mt-1 min-h-16 rounded-md border border-border bg-card px-3 py-2 text-sm text-foreground"
        textAlignVertical="top"
      />
    </View>
  );
}

function PastCard({ c }: { c: CheckIn }) {
  return (
    <Card>
      <View className="flex-row items-center justify-between">
        <Text className="text-sm font-medium text-foreground">Week of {c.week_of}</Text>
        <Text className="text-sm font-semibold text-muted-foreground tabular-nums">{c.mood} · {moodLabel(c.mood)}</Text>
      </View>
      {c.wins ? <Text className="mt-1 text-sm text-foreground"><Text className="text-muted-foreground">Wins: </Text>{c.wins}</Text> : null}
      {c.blockers ? <Text className="mt-0.5 text-sm text-foreground"><Text className="text-muted-foreground">Blockers: </Text>{c.blockers}</Text> : null}
      {c.response ? (
        <View className="mt-2 rounded-md border border-border bg-muted/40 p-2.5">
          <View className="flex-row flex-wrap items-center gap-1.5">
            <Text className="text-2xs font-semibold text-muted-foreground">{c.response.responder.display} responded</Text>
            {c.response.follow_up ? <Badge tone="warning">Follow-up</Badge> : null}
            {c.response.add_to_one_on_one ? <Badge>For 1-on-1</Badge> : null}
          </View>
          {c.response.comment ? <Text className="mt-1 text-sm text-foreground">{c.response.comment}</Text> : null}
        </View>
      ) : null}
    </Card>
  );
}
