import * as React from "react";
import { RefreshControl, ScrollView, Text, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { reviewsApi } from "@shared/api/endpoints";
import { humanize } from "@shared/enums";
import type { Review } from "@shared/types";
import { Badge, Card, EmptyView, ErrorView, Loading, SectionTitle } from "@/components/ui";

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
 *  finalized, else the working draft). The body is rendered as DESIGNED SECTIONS
 *  (headings → paragraphs/bullets), never a raw markdown blob. Scope is server-side. */
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
        <EmptyView title="No reviews yet" description="Your performance reviews will appear here once your manager prepares one." />
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
        <ReviewBody body={body} />
      ) : (
        <Text className="mt-2 text-sm text-muted-foreground">No content yet — this review is still being prepared.</Text>
      )}
    </Card>
  );
}

/** Render the review body as designed sections instead of a raw blob: markdown-style
 *  headings (`#`/`##`/`**Heading**`) become section labels; `-`/`*` lines become
 *  bullets; blank lines break paragraphs. Presentation only — the text is unchanged. */
function ReviewBody({ body }: { body: string }) {
  const sections = parseSections(body);
  return (
    <View className="mt-3 gap-4">
      {sections.map((s, i) => (
        <View key={i} className="gap-1.5">
          {s.heading ? <SectionTitle>{s.heading}</SectionTitle> : null}
          {renderLines(s.lines)}
        </View>
      ))}
    </View>
  );
}

function parseSections(md: string): { heading: string | null; lines: string[] }[] {
  const out: { heading: string | null; lines: string[] }[] = [];
  let cur: { heading: string | null; lines: string[] } = { heading: null, lines: [] };
  for (const raw of md.split(/\r?\n/)) {
    const line = raw.trimEnd();
    const h = line.match(/^#{1,4}\s+(.*)$/) || line.match(/^\*\*(.+?)\*\*:?\s*$/);
    if (h) {
      if (cur.heading || cur.lines.some((l) => l.trim())) out.push(cur);
      cur = { heading: clean(h[1]), lines: [] };
    } else {
      cur.lines.push(line);
    }
  }
  if (cur.heading || cur.lines.some((l) => l.trim())) out.push(cur);
  return out.length ? out : [{ heading: null, lines: md.split(/\r?\n/) }];
}

function clean(s: string): string {
  return s.replace(/\*\*/g, "").trim();
}

function renderLines(lines: string[]): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  let para: string[] = [];
  const flush = (key: string) => {
    if (para.length) {
      out.push(
        <Text key={key} className="text-sm leading-relaxed text-foreground">{clean(para.join(" "))}</Text>,
      );
      para = [];
    }
  };
  lines.forEach((line, i) => {
    const t = line.trim();
    if (!t) {
      flush(`p${i}`);
      return;
    }
    const b = t.match(/^[-*]\s+(.*)$/);
    if (b) {
      flush(`p${i}`);
      out.push(
        <View key={`b${i}`} className="flex-row gap-2">
          <Text className="text-sm leading-relaxed text-primary">{"•"}</Text>
          <Text className="flex-1 text-sm leading-relaxed text-foreground">{clean(b[1])}</Text>
        </View>,
      );
    } else {
      para.push(t);
    }
  });
  flush("pend");
  return out;
}
