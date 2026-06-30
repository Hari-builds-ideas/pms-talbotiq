import * as React from "react";
import { Pressable, RefreshControl, ScrollView, Text, TextInput, View } from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { orgApi, recognitionApi } from "@shared/api/endpoints";
import type { PersonRef, RecognitionCard as Card_, RecognitionVisibility } from "@shared/types";
import { Badge, Button, Card, EmptyView, ErrorView, Icon, Loading } from "@/components/ui";

const EMOJI = ["👏", "❤️", "🎉"];

/** Recognition — give kudos (recipient resolved within your visible org, value + message +
 *  visibility) and browse the feed you're permitted to see, with one-tap reactions. All via
 *  the same audited endpoints + server-side visibility/scope the web uses. */
export default function Recognition() {
  const q = useQuery({ queryKey: ["recognition", "feed"], queryFn: recognitionApi.feed });
  const feed = q.data ?? [];

  return (
    <ScrollView
      className="flex-1 bg-background"
      contentContainerClassName="p-5 gap-4"
      keyboardShouldPersistTaps="handled"
      refreshControl={<RefreshControl refreshing={q.isFetching} onRefresh={() => q.refetch()} tintColor="#0d5c3a" />}
    >
      <GiveRecognition />
      {q.isLoading ? (
        <Loading label="Loading recognition…" />
      ) : q.isError ? (
        <ErrorView error={q.error} onRetry={() => q.refetch()} />
      ) : feed.length === 0 ? (
        <EmptyView title="No recognition yet" description="Be the first to give kudos to a teammate." />
      ) : (
        feed.map((c) => <KudoCard key={c.id} card={c} />)
      )}
    </ScrollView>
  );
}

function GiveRecognition() {
  const qc = useQueryClient();
  const [open, setOpen] = React.useState(false);
  const [term, setTerm] = React.useState("");
  const [recipient, setRecipient] = React.useState<PersonRef | null>(null);
  const [value, setValue] = React.useState("");
  const [message, setMessage] = React.useState("");
  const [visibility, setVisibility] = React.useState<RecognitionVisibility>("TEAM");

  const meta = useQuery({ queryKey: ["recognition", "meta"], queryFn: recognitionApi.meta, enabled: open });
  const results = useQuery({
    queryKey: ["org", "search", term],
    queryFn: () => orgApi.search(term),
    enabled: open && !recipient && term.trim().length >= 2,
  });

  const give = useMutation({
    mutationFn: () =>
      recognitionApi.give({ recipient: recipient!.id, value, message: message.trim(), visibility }),
    onSuccess: () => {
      setOpen(false);
      setRecipient(null);
      setTerm("");
      setValue("");
      setMessage("");
      void qc.invalidateQueries({ queryKey: ["recognition"] });
    },
  });

  if (!open) {
    return <Button title="Give recognition" variant="outline" onPress={() => setOpen(true)} />;
  }

  const canSend = recipient && value && message.trim().length > 0;
  return (
    <Card>
      <View className="flex-row items-center justify-between">
        <Text className="text-base font-semibold text-foreground">Give recognition</Text>
        <Pressable onPress={() => setOpen(false)} hitSlop={8}><Icon name="x" size={20} /></Pressable>
      </View>

      {/* Recipient — resolved only within what you can see (server-scoped search). */}
      {recipient ? (
        <View className="mt-2 flex-row items-center justify-between rounded-md border border-border bg-muted/40 px-3 py-2">
          <Text className="text-sm font-medium text-foreground">{recipient.display}</Text>
          <Pressable onPress={() => setRecipient(null)}><Text className="text-2xs text-primary">change</Text></Pressable>
        </View>
      ) : (
        <View className="mt-2">
          <TextInput
            value={term}
            onChangeText={setTerm}
            placeholder="Search a teammate by name…"
            className="rounded-md border border-border bg-card px-3 py-2 text-sm text-foreground"
          />
          {results.data?.results.slice(0, 6).map((p) => (
            <Pressable key={p.id} onPress={() => setRecipient(p)} className="border-b border-border px-1 py-2">
              <Text className="text-sm text-foreground">{p.display}</Text>
              {p.title ? <Text className="text-2xs text-muted-foreground">{p.title}</Text> : null}
            </Pressable>
          ))}
        </View>
      )}

      {/* Value */}
      <Text className="mt-3 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">Value</Text>
      <View className="mt-1 flex-row flex-wrap gap-2">
        {(meta.data?.values ?? []).map((v) => (
          <Chip key={v} on={value === v} label={v} onPress={() => setValue(v)} />
        ))}
      </View>

      {/* Message */}
      <TextInput
        value={message}
        onChangeText={setMessage}
        placeholder="What did they do? Be specific."
        multiline
        className="mt-3 min-h-16 rounded-md border border-border bg-card px-3 py-2 text-sm text-foreground"
        textAlignVertical="top"
      />

      {/* Visibility */}
      <Text className="mt-3 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">Visibility</Text>
      <View className="mt-1 flex-row flex-wrap gap-2">
        {(meta.data?.visibilities ?? []).map((vis) => (
          <Chip key={vis.value} on={visibility === vis.value} label={vis.label} onPress={() => setVisibility(vis.value)} />
        ))}
      </View>

      {give.isError ? <Text className="mt-2 text-2xs text-danger">Could not send — check the fields.</Text> : null}
      <View className="mt-3">
        <Button title="Send recognition" onPress={() => canSend && give.mutate()} loading={give.isPending} disabled={!canSend} />
      </View>
    </Card>
  );
}

function Chip({ on, label, onPress }: { on: boolean; label: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} className={`rounded-full border px-3 py-1.5 ${on ? "border-primary bg-primary/10" : "border-border bg-muted"}`}>
      <Text className={`text-xs font-medium ${on ? "text-primary" : "text-muted-foreground"}`}>{label}</Text>
    </Pressable>
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
        <View className="flex-1 flex-row items-center gap-1.5">
          <Text className="text-sm font-medium text-foreground" numberOfLines={1}>{card.sender.display}</Text>
          <Icon name="arrow-right" size={13} />
          <Text className="text-sm font-medium text-foreground" numberOfLines={1}>{card.recipient.display}</Text>
        </View>
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
