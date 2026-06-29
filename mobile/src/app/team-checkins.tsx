import * as React from "react";
import { Pressable, RefreshControl, ScrollView, Text, TextInput, View } from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { checkinsApi } from "@shared/api/endpoints";
import type { CheckIn } from "@shared/types";
import { Button, Card, EmptyView, ErrorView, Loading } from "@/components/ui";

const MOOD: Record<number, string> = { 1: "😞", 2: "😕", 3: "😐", 4: "🙂", 5: "😄" };

/** Team check-ins (manager) — read your reports' weekly check-ins and respond
 *  (comment + follow-up / add-to-1-on-1) via the same audited endpoint the web uses.
 *  The feed is server-scoped to the manager's reporting subtree. */
export default function TeamCheckins() {
  const q = useQuery({ queryKey: ["checkins", "team"], queryFn: checkinsApi.team });
  const items = q.data ?? [];

  if (q.isLoading) return <Loading label="Loading your team's check-ins…" />;
  if (q.isError) return <ErrorView error={q.error} onRetry={() => q.refetch()} />;

  return (
    <ScrollView
      className="flex-1 bg-background"
      contentContainerClassName="p-5 gap-4"
      keyboardShouldPersistTaps="handled"
      refreshControl={<RefreshControl refreshing={q.isFetching} onRefresh={() => q.refetch()} tintColor="#5B5BD6" />}
    >
      {items.length === 0 ? (
        <EmptyView title="No check-ins yet" description="When your reports check in, they'll appear here to read and respond." />
      ) : (
        items.map((c) => <TeamCard key={c.id} c={c} />)
      )}
    </ScrollView>
  );
}

function TeamCard({ c }: { c: CheckIn }) {
  const qc = useQueryClient();
  const [comment, setComment] = React.useState(c.response?.comment ?? "");
  const [followUp, setFollowUp] = React.useState(c.response?.follow_up ?? false);
  const [oneOnOne, setOneOnOne] = React.useState(c.response?.add_to_one_on_one ?? false);
  const respond = useMutation({
    mutationFn: () =>
      checkinsApi.respond(c.id, { comment, follow_up: followUp, add_to_one_on_one: oneOnOne }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["checkins"] }),
  });

  return (
    <Card>
      <View className="flex-row items-center justify-between">
        <Text className="text-sm font-semibold text-foreground">{c.author.display}</Text>
        <Text className="text-2xs text-muted-foreground">Week of {c.week_of} · {MOOD[c.mood] ?? "·"}</Text>
      </View>
      {c.wins ? <Text className="mt-1 text-sm text-foreground"><Text className="text-muted-foreground">Wins: </Text>{c.wins}</Text> : null}
      {c.blockers ? <Text className="mt-0.5 text-sm text-foreground"><Text className="text-muted-foreground">Blockers: </Text>{c.blockers}</Text> : null}

      <View className="mt-3 gap-2 border-t border-border pt-3">
        <TextInput
          value={comment}
          onChangeText={setComment}
          placeholder="Respond to this check-in…"
          multiline
          className="min-h-16 rounded-md border border-border bg-card px-3 py-2 text-sm text-foreground"
          textAlignVertical="top"
        />
        <View className="flex-row gap-2">
          <Toggle on={followUp} onPress={() => setFollowUp((v) => !v)} label="Needs follow-up" />
          <Toggle on={oneOnOne} onPress={() => setOneOnOne((v) => !v)} label="Add to 1-on-1" />
        </View>
        <Button title={c.response ? "Update response" : "Respond"} onPress={() => respond.mutate()} loading={respond.isPending} />
      </View>
    </Card>
  );
}

function Toggle({ on, onPress, label }: { on: boolean; onPress: () => void; label: string }) {
  return (
    <Pressable onPress={onPress} className={`rounded-full border px-3 py-1.5 ${on ? "border-primary bg-primary/10" : "border-border bg-muted"}`}>
      <Text className={`text-xs font-medium ${on ? "text-primary" : "text-muted-foreground"}`}>{on ? "✓ " : ""}{label}</Text>
    </Pressable>
  );
}
