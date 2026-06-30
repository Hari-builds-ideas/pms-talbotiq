import * as React from "react";
import { RefreshControl, ScrollView, Text, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { reviewsApi } from "@shared/api/endpoints";
import { humanize } from "@shared/enums";
import type { Review } from "@shared/types";
import { Badge, Card, EmptyView, ErrorView, Loading } from "@/components/ui";

type Tone = "muted" | "primary" | "success" | "warning" | "danger" | "ai";
const STATE_TONE: Record<string, Tone> = {
  DRAFT: "muted",
  EDITING: "muted",
  AI_DRAFTING: "ai",
  PENDING_HUMAN_REVIEW: "warning",
  APPROVED: "primary",
  FINALIZED: "success",
  REJECTED: "danger",
};

/** My performance reviews — read-only: state + the body once it's written (final if
 *  finalized, else the working draft). Scope is server-side (you see only your own). */
export default function Reviews() {
  const q = useQuery({ queryKey: ["reviews", "mine"], queryFn: () => reviewsApi.list({ page_size: 20 }) });
  const reviews = q.data?.results ?? [];

  if (q.isLoading) return <Loading label="Loading your reviews…" />;
  if (q.isError) return <ErrorView error={q.error} onRetry={() => q.refetch()} />;

  return (
    <ScrollView
      className="flex-1 bg-background"
      contentContainerClassName="p-5 gap-4"
      refreshControl={<RefreshControl refreshing={q.isFetching} onRefresh={() => q.refetch()} tintColor="#0d5c3a" />}
    >
      {reviews.length === 0 ? (
        <EmptyView title="No reviews yet" description="Your performance reviews will appear here." />
      ) : (
        reviews.map((r) => <ReviewCard key={r.id} review={r} />)
      )}
    </ScrollView>
  );
}

function ReviewCard({ review }: { review: Review }) {
  const body = review.state === "FINALIZED" ? review.final_body : review.final_body || review.draft_body;
  return (
    <Card>
      <View className="flex-row items-center justify-between gap-2">
        <Text className="flex-1 text-base font-semibold text-foreground">{review.cycle_name ?? "Performance review"}</Text>
        <Badge tone={STATE_TONE[review.state] ?? "muted"}>{humanize(review.state)}</Badge>
      </View>
      {review.rejected_reason ? (
        <Text className="mt-1 text-sm text-danger">Returned: {review.rejected_reason}</Text>
      ) : null}
      {body ? (
        <Text className="mt-2 text-sm leading-relaxed text-foreground">{body}</Text>
      ) : (
        <Text className="mt-2 text-sm text-muted-foreground">No content yet — this review is still being prepared.</Text>
      )}
    </Card>
  );
}
