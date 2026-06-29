import * as React from "react";
import { RefreshControl, ScrollView, Text, TextInput, View } from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { feedbackApi } from "@shared/api/endpoints";
import { humanize } from "@shared/enums";
import type { FeedbackRequestItem, MyFeedbackCycle } from "@shared/types";
import { Badge, Button, Card, EmptyView, ErrorView, Loading, SectionTitle } from "@/components/ui";

/** 360 Feedback — two real loops: (1) requests asking ME to give feedback (submit via the
 *  audited give endpoint), and (2) MY released 360 summary (own-only discovery + the
 *  released sections). Giver identity is never shown; summaries are anonymised server-side. */
export default function Feedback() {
  const requests = useQuery({ queryKey: ["feedback", "requests", "mine"], queryFn: feedbackApi.requestsMine });
  const myCycles = useQuery({ queryKey: ["feedback", "my-cycles"], queryFn: () => feedbackApi.myCycles({ page_size: 50 }) });

  if (requests.isLoading || myCycles.isLoading) return <Loading label="Loading feedback…" />;

  const pending = (requests.data ?? []).filter((r) => r.status === "PENDING");
  const released = (myCycles.data?.results ?? []).filter((c) => c.summary_released && c.summary_id);

  const refreshing = requests.isFetching || myCycles.isFetching;
  const refetchAll = () => {
    void requests.refetch();
    void myCycles.refetch();
  };

  return (
    <ScrollView
      className="flex-1 bg-background"
      contentContainerClassName="p-5 gap-4"
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refetchAll} tintColor="#5B5BD6" />}
    >
      <SectionTitle>Feedback requested from you</SectionTitle>
      {requests.isError ? (
        <ErrorView error={requests.error} onRetry={() => requests.refetch()} />
      ) : pending.length === 0 ? (
        <EmptyView title="Nothing to give right now" description="When someone asks you for 360 feedback, it'll appear here." />
      ) : (
        pending.map((r) => <GiveCard key={r.id} request={r} />)
      )}

      <View className="mt-2">
        <SectionTitle>My 360 summary</SectionTitle>
      </View>
      {released.length === 0 ? (
        <Text className="text-sm text-muted-foreground">No released summary yet.</Text>
      ) : (
        released.map((c) => <MySummaryCard key={c.id} cycle={c} />)
      )}
    </ScrollView>
  );
}

function GiveCard({ request }: { request: FeedbackRequestItem }) {
  const qc = useQueryClient();
  const [body, setBody] = React.useState("");
  const m = useMutation({
    mutationFn: () => feedbackApi.give(request.cycle, { body: body.trim() }),
    onSuccess: () => {
      setBody("");
      void qc.invalidateQueries({ queryKey: ["feedback"] });
    },
  });
  return (
    <Card>
      <View className="flex-row items-center justify-between gap-2">
        <Text className="text-sm font-medium text-foreground">A 360 request for your input</Text>
        <Badge tone="primary">{humanize(request.relationship)}</Badge>
      </View>
      <TextInput
        value={body}
        onChangeText={setBody}
        placeholder="Share specific, balanced, evidence-based feedback…"
        multiline
        className="mt-2 min-h-24 rounded-md border border-border bg-card px-3 py-2 text-sm text-foreground"
        textAlignVertical="top"
      />
      {m.isError ? <Text className="mt-1 text-2xs text-danger">Could not submit — try again.</Text> : null}
      <View className="mt-2">
        <Button title="Submit feedback" onPress={() => body.trim() && m.mutate()} loading={m.isPending} disabled={!body.trim()} />
      </View>
    </Card>
  );
}

function MySummaryCard({ cycle }: { cycle: MyFeedbackCycle }) {
  const q = useQuery({
    queryKey: ["feedback", "summary", cycle.id],
    queryFn: () => feedbackApi.summary(cycle.id),
  });
  const s = q.data?.sections;
  return (
    <Card>
      <Text className="text-sm font-semibold text-foreground">Your released 360 summary</Text>
      {q.isLoading ? (
        <Text className="mt-1 text-2xs text-muted-foreground">Loading…</Text>
      ) : !s ? (
        <Text className="mt-1 text-sm text-muted-foreground">Summary not available.</Text>
      ) : (
        <View className="mt-2 gap-2">
          {(["strengths", "growth", "themes", "risks"] as const).map((k) =>
            s[k] ? (
              <View key={k}>
                <Text className="text-2xs font-semibold uppercase tracking-wide text-muted-foreground">{k}</Text>
                <Text className="mt-0.5 text-sm text-foreground">{s[k]}</Text>
              </View>
            ) : null,
          )}
        </View>
      )}
    </Card>
  );
}
