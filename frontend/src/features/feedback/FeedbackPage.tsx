import * as React from "react";
import {
  CheckCircle2,
  Inbox,
  MessageSquareText,
  Plus,
  Sparkles,
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/Field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { StatusBadge } from "@/components/StatusBadge";
import { PersonName } from "@/components/PersonName";
import { LinesSkeleton } from "@/components/Skeletons";
import { useAuth } from "@/lib/auth/AuthContext";
import { useDirectory } from "@/lib/hooks/useDirectory";
import { humanize } from "@/lib/enums";
import { formatDate } from "@/lib/format";
import { mapApiError } from "@/lib/errors";
import { notifyError, notifySuccess } from "@/lib/toast";
import { GiveFeedbackDialog } from "./GiveFeedbackDialog";
import { CycleSheet } from "./CycleSheet";
import { SummaryView } from "./SummaryView";
import {
  useCycles,
  useFeedbackMutations,
  useMyRequests,
  useMySummary,
  useReviewQueue,
} from "./useFeedback";
import type { FeedbackCycle } from "@/lib/types";

export function FeedbackPage() {
  const { atLeast } = useAuth();
  return (
    <div>
      <PageHeader
        title="360 Feedback"
        description="Request, give and summarise multi-rater feedback. Responses are anonymised and threshold-gated; every AI summary passes a human gate before release."
      />
      <Tabs defaultValue="inbox">
        <TabsList>
          <TabsTrigger value="inbox">For me</TabsTrigger>
          <TabsTrigger value="mine">My 360</TabsTrigger>
          <TabsTrigger value="cycles">Cycles</TabsTrigger>
          {atLeast("HRBP") && <TabsTrigger value="review">Summaries to release</TabsTrigger>}
        </TabsList>
        <TabsContent value="inbox"><InboxTab /></TabsContent>
        <TabsContent value="mine"><My360Tab /></TabsContent>
        <TabsContent value="cycles"><CyclesTab /></TabsContent>
        {atLeast("HRBP") && <TabsContent value="review"><ReviewTab /></TabsContent>}
      </Tabs>
    </div>
  );
}

// ── For me: invitations to give feedback ─────────────────────────────────────
function InboxTab() {
  const q = useMyRequests();
  const { decline } = useFeedbackMutations();
  const [give, setGive] = React.useState<{ cycleId: string; relationship: string } | null>(null);
  const pending = (q.data ?? []).filter((r) => r.status === "PENDING");
  const done = (q.data ?? []).filter((r) => r.status !== "PENDING");

  return (
    <Panel title="Feedback requested from you" icon={Inbox}>
      {q.isLoading ? (
        <LinesSkeleton lines={3} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} compact />
      ) : pending.length === 0 && done.length === 0 ? (
        <EmptyState compact icon={Inbox} title="No requests" description="When someone invites you to give 360 feedback, it appears here." />
      ) : (
        <ul className="divide-y divide-border">
          {pending.map((r) => (
            <li key={r.id} className="flex items-center justify-between gap-3 py-3 first:pt-0">
              <div>
                <p className="text-sm font-medium">{humanize(r.relationship)} feedback requested</p>
                <p className="text-2xs text-muted-foreground">Anonymised · threshold-gated</p>
              </div>
              <div className="flex items-center gap-1.5">
                <Button variant="ghost" size="sm" className="text-danger" onClick={() => decline.mutateAsync(r.id).then(() => notifySuccess("Declined")).catch(notifyError)}>Decline</Button>
                <Button size="sm" onClick={() => setGive({ cycleId: r.cycle, relationship: r.relationship })}>Give feedback</Button>
              </div>
            </li>
          ))}
          {done.map((r) => (
            <li key={r.id} className="flex items-center justify-between gap-3 py-3 first:pt-0">
              <p className="text-sm text-muted-foreground">{humanize(r.relationship)} feedback</p>
              <StatusBadge status={r.status} />
            </li>
          ))}
        </ul>
      )}
      <GiveFeedbackDialog
        open={Boolean(give)}
        onOpenChange={(o) => !o && setGive(null)}
        cycleId={give?.cycleId ?? null}
        relationship={give?.relationship}
      />
    </Panel>
  );
}

// ── My 360: the caller's own released summary (subject) ──────────────────────
function My360Tab() {
  const { me } = useAuth();
  const cycles = useCycles();
  const mine = (cycles.data?.results ?? []).filter((c) => c.subject === me?.id);

  return (
    <div className="space-y-4">
      {cycles.isLoading ? (
        <LinesSkeleton lines={3} />
      ) : cycles.isError ? (
        <ErrorState error={cycles.error} onRetry={() => cycles.refetch()} />
      ) : mine.length === 0 ? (
        <EmptyState
          icon={MessageSquareText}
          title="No 360 about you yet"
          description="When a 360 cycle is run for you and the summary is released, you'll see it here."
        />
      ) : (
        mine.map((c) => <MySummaryCard key={c.id} cycle={c} />)
      )}
    </div>
  );
}

function MySummaryCard({ cycle }: { cycle: FeedbackCycle }) {
  const q = useMySummary(cycle.id);
  return (
    <Panel title="Your 360 summary" icon={MessageSquareText} aside={<StatusBadge status={cycle.status} />}>
      {q.isLoading ? (
        <LinesSkeleton lines={4} />
      ) : q.isError ? (
        mapApiError(q.error).code === "SUMMARY_NOT_RELEASED" ? (
          <EmptyState compact icon={MessageSquareText} title="Not released yet" description="Your summary is being reviewed by HR. You'll see it here once it's released." />
        ) : mapApiError(q.error).kind === "not_found" ? (
          <EmptyState compact icon={MessageSquareText} title="No summary yet" description="The cycle hasn't been summarised yet." />
        ) : (
          <ErrorState error={q.error} onRetry={() => q.refetch()} compact />
        )
      ) : q.data ? (
        <SummaryView summary={q.data} />
      ) : null}
    </Panel>
  );
}

// ── Cycles: manage (Manager+) ─────────────────────────────────────────────────
function CyclesTab() {
  const cycles = useCycles();
  const [createOpen, setCreateOpen] = React.useState(false);
  const [selected, setSelected] = React.useState<FeedbackCycle | null>(null);
  const rows = cycles.data?.results ?? [];

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setCreateOpen(true)}><Plus className="h-4 w-4" /> New cycle</Button>
      </div>
      {cycles.isLoading ? (
        <LinesSkeleton lines={4} />
      ) : cycles.isError ? (
        <ErrorState error={cycles.error} onRetry={() => cycles.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState icon={MessageSquareText} title="No feedback cycles" description="Open a 360 cycle for someone on your team and invite reviewers." action={<Button onClick={() => setCreateOpen(true)}>New cycle</Button>} />
      ) : (
        <Panel title="Feedback cycles" icon={MessageSquareText}>
          <ul className="divide-y divide-border">
            {rows.map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
                <div className="min-w-0">
                  <p className="text-sm font-medium">360 for <PersonName id={c.subject} /></p>
                  <p className="text-2xs text-muted-foreground">
                    min volume {c.min_volume ?? 3}{c.opened_at ? ` · opened ${formatDate(c.opened_at)}` : ""}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge status={c.status} dot />
                  <Button variant="outline" size="sm" onClick={() => setSelected(c)}>Manage</Button>
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      <CreateCycleDialog open={createOpen} onOpenChange={setCreateOpen} />
      <CycleSheet cycle={selected} onOpenChange={(o) => !o && setSelected(null)} />
    </div>
  );
}

function CreateCycleDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { nodes } = useDirectory();
  const { createCycle, openCycle } = useFeedbackMutations();
  const [subject, setSubject] = React.useState("");
  const [minVolume, setMinVolume] = React.useState("3");
  const [openNow, setOpenNow] = React.useState(true);

  React.useEffect(() => {
    if (open) { setSubject(""); setMinVolume("3"); setOpenNow(true); }
  }, [open]);

  async function submit() {
    try {
      const cycle = await createCycle.mutateAsync({ subject, min_volume: Number(minVolume) || undefined });
      if (openNow) await openCycle.mutateAsync(cycle.id);
      notifySuccess("Cycle created", openNow ? "Now invite reviewers." : "Open it to start collecting.");
      onOpenChange(false);
    } catch (err) {
      notifyError(err);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>New 360 cycle</DialogTitle>
          <DialogDescription>Open a feedback cycle for someone in your scope.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <Field label="Subject" required>
            <Select value={subject} onValueChange={setSubject}>
              <SelectTrigger><SelectValue placeholder="Select a person…" /></SelectTrigger>
              <SelectContent>
                {Object.values(nodes).map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.display}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Minimum volume per group" hint="A relationship group is shown only at/above this count (anonymity).">
            <Input value={minVolume} onChange={(e) => setMinVolume(e.target.value)} inputMode="numeric" className="w-24" />
          </Field>
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <input type="checkbox" checked={openNow} onChange={(e) => setOpenNow(e.target.checked)} className="h-4 w-4 rounded border-input" />
            Open immediately for collection
          </label>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} loading={createCycle.isPending || openCycle.isPending} disabled={!subject}>Create</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── HRBP: summaries to release ────────────────────────────────────────────────
function ReviewTab() {
  const q = useReviewQueue();
  const { approveSummary } = useFeedbackMutations();
  const rows = q.data?.results ?? [];

  return (
    <div className="space-y-4">
      {q.isLoading ? (
        <LinesSkeleton lines={4} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState icon={CheckCircle2} title="Nothing to release" description="AI feedback summaries awaiting your review (PENDING or held) appear here." />
      ) : (
        rows.map((s) => (
          <Panel
            key={s.id}
            title="AI feedback summary"
            icon={Sparkles}
            aside={<span className="flex items-center gap-1.5 text-2xs text-muted-foreground">for <PersonName id={s.subject} className="font-semibold text-foreground" /></span>}
          >
            <div className="space-y-3">
              <SummaryView summary={s} showHitl />
              <div className="flex justify-end border-t border-border pt-3">
                <Button
                  onClick={() => approveSummary.mutateAsync(s.id).then(() => notifySuccess("Summary released", "The subject can now see it.")).catch(notifyError)}
                  loading={approveSummary.isPending}
                >
                  <CheckCircle2 className="h-4 w-4" /> Release to subject
                </Button>
              </div>
            </div>
          </Panel>
        ))
      )}
    </div>
  );
}
