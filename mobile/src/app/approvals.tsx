import * as React from "react";
import { RefreshControl, ScrollView, Text, TextInput, View } from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { approvalsApi } from "@shared/api/endpoints";
import { humanize } from "@shared/enums";
import type { InboxItem } from "@shared/types";
import { Badge, Button, Card, EmptyView, ErrorView, Loading } from "@/components/ui";

/** Approvals inbox — the steps awaiting MY decision. Approve (optional comment) or
 *  reject (reason required) via the same audited approval endpoints the web uses;
 *  scope is server-side (an employee's inbox is empty / 403). */
export default function Approvals() {
  const q = useQuery({ queryKey: ["approvals", "inbox"], queryFn: approvalsApi.inbox });
  const items = q.data ?? [];

  if (q.isLoading) return <Loading label="Loading your inbox…" />;
  if (q.isError) return <ErrorView error={q.error} onRetry={() => q.refetch()} />;

  return (
    <ScrollView
      className="flex-1 bg-background"
      contentContainerClassName="p-5 gap-4"
      keyboardShouldPersistTaps="handled"
      refreshControl={<RefreshControl refreshing={q.isFetching} onRefresh={() => q.refetch()} tintColor="#0d5c3a" />}
    >
      {items.length === 0 ? (
        <EmptyView title="Inbox zero" description="No approvals are awaiting your decision." />
      ) : (
        items.map((it) => <InboxCard key={it.id} item={it} />)
      )}
    </ScrollView>
  );
}

function InboxCard({ item }: { item: InboxItem }) {
  const qc = useQueryClient();
  const [rejecting, setRejecting] = React.useState(false);
  const [reason, setReason] = React.useState("");
  const done = () => void qc.invalidateQueries({ queryKey: ["approvals"] });
  const approve = useMutation({ mutationFn: () => approvalsApi.approveStep(item.id), onSuccess: done });
  const reject = useMutation({ mutationFn: () => approvalsApi.rejectStep(item.id, reason.trim()), onSuccess: done });

  return (
    <Card>
      <View className="flex-row items-center justify-between gap-2">
        <Text className="flex-1 text-base font-semibold text-foreground">{humanize(item.artifact_type)} approval</Text>
        {item.escalated ? <Badge tone="danger">Escalated</Badge> : <Badge tone="warning">Step {item.order + 1}</Badge>}
      </View>
      <Text className="mt-0.5 text-2xs text-muted-foreground">Ref {item.artifact_id.slice(0, 8)}</Text>

      {rejecting ? (
        <View className="mt-2 gap-2">
          <TextInput
            value={reason}
            onChangeText={setReason}
            placeholder="Reason for rejecting…"
            multiline
            className="min-h-16 rounded-md border border-border bg-card px-3 py-2 text-sm text-foreground"
            textAlignVertical="top"
          />
          <View className="flex-row gap-2">
            <Button title="Confirm reject" variant="danger" onPress={() => reason.trim() && reject.mutate()} loading={reject.isPending} disabled={!reason.trim()} className="flex-1" />
            <Button title="Cancel" variant="outline" onPress={() => setRejecting(false)} className="flex-1" />
          </View>
        </View>
      ) : (
        <View className="mt-3 flex-row gap-2">
          <Button title="Approve" onPress={() => approve.mutate()} loading={approve.isPending} className="flex-1" />
          <Button title="Reject" variant="outline" onPress={() => setRejecting(true)} className="flex-1" />
        </View>
      )}
    </Card>
  );
}
