import * as React from "react";
import { useMutation } from "@tanstack/react-query";
import { CalendarCheck, ListChecks, MessageSquare, Sparkles } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Field } from "@/components/Field";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CardGridSkeleton } from "@/components/Skeletons";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { aiApi } from "@/lib/api/endpoints";
import { mapApiError } from "@/lib/errors";
import { useAuth } from "@/lib/auth/AuthContext";
import { notifyError, notifySuccess } from "@/lib/toast";
import type { CheckIn, MeetingSummary } from "@/lib/types";
import {
  mondayOf,
  useCheckinMutations,
  useMyCheckins,
  useTeamCheckins,
} from "./useCheckins";

const MOODS = [
  { v: 1, e: "😞" },
  { v: 2, e: "😕" },
  { v: 3, e: "😐" },
  { v: 4, e: "🙂" },
  { v: 5, e: "😄" },
];
const moodEmoji = (m: number) => MOODS.find((x) => x.v === m)?.e ?? "·";
const toLines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);

export function CheckInsPage() {
  const { atLeast } = useAuth();
  const isManager = atLeast("MANAGER");
  return (
    <div>
      <PageHeader
        eyebrow="Performance" title="Check-ins"
        description="A quick weekly pulse — your mood, wins, blockers and priorities. Your manager reads and responds."
      />
      <Tabs defaultValue="mine">
        <TabsList>
          <TabsTrigger value="mine">My check-ins</TabsTrigger>
          {isManager && <TabsTrigger value="team">My team</TabsTrigger>}
        </TabsList>
        <TabsContent value="mine"><MyCheckinsTab /></TabsContent>
        {isManager && <TabsContent value="team"><TeamCheckinsTab /></TabsContent>}
      </Tabs>
    </div>
  );
}

// ── My check-ins ──────────────────────────────────────────────────────────────
function MyCheckinsTab() {
  const q = useMyCheckins();
  const m = useCheckinMutations();
  const week = mondayOf();
  const mine = q.data ?? [];
  const thisWeek = mine.find((c) => c.week_of === week);

  const [mood, setMood] = React.useState(0);
  const [wins, setWins] = React.useState("");
  const [blockers, setBlockers] = React.useState("");
  const [learning, setLearning] = React.useState("");
  const [priorities, setPriorities] = React.useState("");

  // Prefill from this week's existing check-in (edit in place).
  React.useEffect(() => {
    if (thisWeek) {
      setMood(thisWeek.mood);
      setWins(thisWeek.wins);
      setBlockers(thisWeek.blockers);
      setLearning(thisWeek.learning);
      setPriorities(thisWeek.priorities.map((p) => p.text).join("\n"));
    }
  }, [thisWeek]);

  async function save() {
    try {
      await m.save.mutateAsync({
        week_of: week,
        mood,
        wins,
        blockers,
        learning,
        priorities: toLines(priorities).map((text) => ({ text, status: "ACTIVE" as const })),
      });
      notifySuccess(thisWeek ? "Check-in updated" : "Check-in shared");
    } catch (err) {
      notifyError(err);
    }
  }

  const past = mine.filter((c) => c.week_of !== week);

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <Card>
        <CardContent className="space-y-4 p-4">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <CalendarCheck className="h-4 w-4 text-primary" /> This week ({week})
          </div>
          <Field label="How was your week?" required>
            <div className="flex gap-1.5">
              {MOODS.map((x) => (
                <button
                  key={x.v}
                  type="button"
                  aria-label={`Mood ${x.v}`}
                  aria-pressed={mood === x.v}
                  onClick={() => setMood(x.v)}
                  className={`tap-target flex h-10 w-10 items-center justify-center rounded-md border text-lg transition-colors ${
                    mood === x.v ? "border-primary bg-primary/10" : "border-border hover:bg-secondary"
                  }`}
                >
                  {x.e}
                </button>
              ))}
            </div>
          </Field>
          <Field label="Wins"><Textarea value={wins} onChange={(e) => setWins(e.target.value)} className="min-h-16" placeholder="What went well?" /></Field>
          <Field label="Blockers"><Textarea value={blockers} onChange={(e) => setBlockers(e.target.value)} className="min-h-16" placeholder="What's in your way?" /></Field>
          <Field label="Learning"><Textarea value={learning} onChange={(e) => setLearning(e.target.value)} className="min-h-12" placeholder="Anything you learned?" /></Field>
          <Field label="Priorities (one per line)"><Textarea value={priorities} onChange={(e) => setPriorities(e.target.value)} className="min-h-16" placeholder="Top things for next week" /></Field>
          <div className="flex justify-end">
            <Button onClick={save} loading={m.save.isPending} disabled={!mood}>
              {thisWeek ? "Update check-in" : "Share check-in"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {q.isLoading ? (
        <CardGridSkeleton count={2} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : past.length > 0 ? (
        <div className="space-y-3">
          <p className="text-2xs font-semibold uppercase tracking-wide text-muted-foreground">Earlier weeks</p>
          {past.map((c) => <CheckInCard key={c.id} c={c} />)}
        </div>
      ) : null}
    </div>
  );
}

function CheckInCard({ c }: { c: CheckIn }) {
  return (
    <Card>
      <CardContent className="space-y-2 p-4">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">Week of {c.week_of}</span>
          <span className="text-lg" title={`Mood ${c.mood}/5`}>{moodEmoji(c.mood)}</span>
        </div>
        {c.wins && <p className="text-sm"><span className="text-muted-foreground">Wins: </span>{c.wins}</p>}
        {c.blockers && <p className="text-sm"><span className="text-muted-foreground">Blockers: </span>{c.blockers}</p>}
        {c.priorities.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {c.priorities.map((p) => (
              <Badge key={p.id} variant="muted">{p.text}</Badge>
            ))}
          </div>
        )}
        {c.response && (
          <div className="mt-2 rounded-md border border-border bg-secondary/40 px-3 py-2 text-sm">
            <div className="flex items-center gap-1.5 text-2xs font-semibold text-muted-foreground">
              <MessageSquare className="h-3 w-3" /> {c.response.responder.display} responded
              {c.response.follow_up && <Badge variant="warning">Follow-up</Badge>}
              {c.response.add_to_one_on_one && <Badge variant="secondary">For 1-on-1</Badge>}
            </div>
            {c.response.comment && <p className="mt-1">{c.response.comment}</p>}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ── Manager: team check-ins ─────────────────────────────────────────────────────
function TeamCheckinsTab() {
  const q = useTeamCheckins(true);
  const items = q.data ?? [];
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <MeetingSummaryCard />
      {q.isLoading ? (
        <CardGridSkeleton count={3} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState icon={CalendarCheck} title="No check-ins from your team yet" description="When your reports check in, they'll appear here for you to read and respond." />
      ) : (
        <div className="space-y-3">
          {items.map((c) => <TeamCheckInCard key={c.id} c={c} />)}
        </div>
      )}
    </div>
  );
}

/**
 * Manager-only AI helper (RW_BUILD_5 quick win): paste 1-on-1 / meeting notes and
 * get a concise summary + concrete action items. The draft is HITL — it persists
 * NOTHING; the manager keeps and uses it. Lives only in the manager "My team" tab,
 * so it's never shown to employees. Errors are kind-aware: a missing AI provider
 * (503) or an exhausted budget (429) render inline; anything else toasts.
 */
function MeetingSummaryCard() {
  const [notes, setNotes] = React.useState("");
  const [result, setResult] = React.useState<MeetingSummary | null>(null);
  const [unavailable, setUnavailable] = React.useState<string | null>(null);

  const m = useMutation({
    mutationFn: (text: string) => aiApi.meetingSummary(text),
    onSuccess: (res) => {
      setResult(res.summary);
      setUnavailable(null);
    },
    onError: (err) => {
      const mapped = mapApiError(err);
      setResult(null);
      if (mapped.kind === "ai_unavailable" || mapped.kind === "rate_limited") {
        setUnavailable(mapped.message);
      } else {
        notifyError(err);
      }
    },
  });

  function summarise() {
    const text = notes.trim();
    if (!text) return;
    setUnavailable(null);
    m.mutate(text);
  }

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Sparkles className="h-4 w-4 text-ai" /> Summarise 1-on-1 / meeting notes
        </div>
        <p className="text-xs text-muted-foreground">
          Paste your raw notes — the assistant drafts a short summary and action items.
          It’s a draft for you; nothing is saved or shared.
        </p>
        <Field label="Notes">
          <Textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="min-h-24"
            placeholder="Paste your 1-on-1 or meeting notes…"
            aria-label="Meeting notes"
          />
        </Field>
        <div className="flex justify-end">
          <Button onClick={summarise} loading={m.isPending} disabled={!notes.trim()}>
            <Sparkles className="mr-1.5 h-4 w-4" /> Summarise with AI
          </Button>
        </div>

        {unavailable && (
          <Alert variant="ai">
            <Sparkles />
            <AlertTitle>AI summary unavailable</AlertTitle>
            <AlertDescription>{unavailable}</AlertDescription>
          </Alert>
        )}

        {result && (
          <div className="space-y-3 rounded-md border border-ai/30 bg-ai-subtle/40 p-3">
            <div>
              <p className="text-2xs font-semibold uppercase tracking-wide text-muted-foreground">Summary</p>
              <p className="mt-1 whitespace-pre-wrap break-words text-sm">{result.summary}</p>
            </div>
            {result.action_items.length > 0 && (
              <div>
                <p className="flex items-center gap-1 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <ListChecks className="h-3 w-3" /> Action items
                </p>
                <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm">
                  {result.action_items.map((a, i) => <li key={i}>{a}</li>)}
                </ul>
              </div>
            )}
            <p className="text-2xs italic text-muted-foreground">Draft — review before you act on it. Nothing was saved.</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function TeamCheckInCard({ c }: { c: CheckIn }) {
  const m = useCheckinMutations();
  const [comment, setComment] = React.useState(c.response?.comment ?? "");
  const [followUp, setFollowUp] = React.useState(c.response?.follow_up ?? false);
  const [oneOnOne, setOneOnOne] = React.useState(c.response?.add_to_one_on_one ?? false);

  async function respond() {
    try {
      await m.respond.mutateAsync({ id: c.id, body: { comment, follow_up: followUp, add_to_one_on_one: oneOnOne } });
      notifySuccess("Response sent");
    } catch (err) {
      notifyError(err);
    }
  }

  return (
    <Card>
      <CardContent className="space-y-2 p-4">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold">{c.author.display}</span>
          <span className="text-2xs text-muted-foreground">Week of {c.week_of} · {moodEmoji(c.mood)}</span>
        </div>
        {c.wins && <p className="text-sm"><span className="text-muted-foreground">Wins: </span>{c.wins}</p>}
        {c.blockers && <p className="text-sm"><span className="text-muted-foreground">Blockers: </span>{c.blockers}</p>}
        <div className="space-y-2 border-t border-border pt-2">
          <Textarea value={comment} onChange={(e) => setComment(e.target.value)} className="min-h-12" placeholder="Respond to this check-in…" />
          <div className="flex flex-wrap items-center gap-4 text-xs">
            <label className="flex items-center gap-1.5">
              <input type="checkbox" checked={followUp} onChange={(e) => setFollowUp(e.target.checked)} /> Needs follow-up
            </label>
            <label className="flex items-center gap-1.5">
              <input type="checkbox" checked={oneOnOne} onChange={(e) => setOneOnOne(e.target.checked)} /> Add to 1-on-1
            </label>
            <Button size="sm" className="ml-auto" onClick={respond} loading={m.respond.isPending}>
              {c.response ? "Update response" : "Respond"}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
