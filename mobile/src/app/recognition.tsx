import * as React from "react";
import { Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { recognitionApi } from "@shared/api/endpoints";
import type { RecognitionCard as Card_ } from "@shared/types";
import { Badge, Card, EmptyView, ErrorView, Loading } from "@/components/ui";

const EMOJI = ["👏", "❤️", "🎉"];

/** Recognition feed — the kudos the caller is permitted to see (visibility enforced
 *  server-side), with one-tap reactions (the same react endpoint the web uses). */
export default function Recognition() {
  const q = useQuery({ queryKey: ["recognition", "feed"], queryFn: recognitionApi.feed });
  const feed = q.data ?? [];

  if (q.isLoading) return <Loading label="Loading recognition…" />;
  if (q.isError) return <ErrorView error={q.error} onRetry={() => q.refetch()} />;

  return (
    <ScrollView
      className="flex-1 bg-background"
      contentContainerClassName="p-5 gap-4"
      refreshControl={<RefreshControl refreshing={q.isFetching} onRefresh={() => q.refetch()} tintColor="#5B5BD6" />}
    >
      {feed.length === 0 ? (
        <EmptyView title="No recognition yet" description="Kudos shared across your team will show up here." />
      ) : (
        feed.map((c) => <KudoCard key={c.id} card={c} />)
      )}
    </ScrollView>
  );
}

function KudoCard({ card }: { card: Card_ }) {
  const qc = useQueryClient();
  const react = useMutation({
    mutationFn: (emoji: string) => recognitionApi.react(card.id, emoji),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["recognition"] }),
  });
  return (
    <Card>
      <View className="flex-row items-center justify-between gap-2">
        <Text className="flex-1 text-sm font-medium text-foreground">
          {card.sender.display} → {card.recipient.display}
        </Text>
        <Badge tone="primary">{card.value}</Badge>
      </View>
      <Text className="mt-1.5 text-sm text-foreground">{card.message}</Text>
      <View className="mt-3 flex-row gap-2">
        {EMOJI.map((e) => {
          const count = card.reactions.counts[e] ?? 0;
          const mine = card.reactions.mine.includes(e);
          return (
            <Pressable
              key={e}
              onPress={() => react.mutate(e)}
              disabled={react.isPending}
              className={`flex-row items-center gap-1 rounded-full border px-2.5 py-1 ${mine ? "border-primary bg-primary/10" : "border-border bg-muted"}`}
            >
              <Text className="text-sm">{e}</Text>
              {count > 0 ? <Text className="text-2xs text-muted-foreground">{count}</Text> : null}
            </Pressable>
          );
        })}
      </View>
    </Card>
  );
}
