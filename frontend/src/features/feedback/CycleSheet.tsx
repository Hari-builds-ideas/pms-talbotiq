import * as React from "react";
import { Lock, Send, ShieldCheck, Sparkles, UserPlus } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Field } from "@/components/Field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LinesSkeleton } from "@/components/Skeletons";
import { StatusBadge } from "@/components/StatusBadge";
import { PersonName } from "@/components/PersonName";
import { useAnonymized, useFeedbackMutations, useInvitations } from "./useFeedback";
import { useDirectory } from "@/lib/hooks/useDirectory";
import { FEEDBACK_RELATIONSHIP, humanize } from "@/lib/enums";
import { mapApiError } from "@/lib/errors";
import { notifyError, notifySuccess } from "@/lib/toast";
import type { FeedbackCycle } from "@/lib/types";

export function CycleSheet({
  cycle,
  onOpenChange,
}: {
  cycle: FeedbackCycle | null;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Sheet open={Boolean(cycle)} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-lg">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            {cycle && <>360 for <PersonName id={cycle.subject} /></>}
            {cycle && <StatusBadge status={cycle.status} dot />}
          </SheetTitle>
          <SheetDescription>
            Invite reviewers, then close to generate an anonymised AI summary (HITL).
          </SheetDescription>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto scrollbar-thin p-5">
          {cycle && <CycleBody cycle={cycle} />}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function CycleBody({ cycle }: { cycle: FeedbackCycle }) {
  const m = useFeedbackMutations();
  const invitations = useInvitations(cycle.id);
  const anonymized = useAnonymized(cycle.id, cycle.status === "CLOSED");
  const [lastResult, setLastResult] = React.useState<{ reason?: string; status?: string; summarized?: boolean } | null>(null);
  const [noProvider, setNoProvider] = React.useState(false);

  const isDraft = cycle.status === "DRAFT";
  const isCollecting = cycle.status === "COLLECTING";
  const isClosed = cycle.status === "CLOSED";

  async function close() {
    setNoProvider(false);
    try {
      const res = await m.closeCycle.mutateAsync(cycle.id);
      setLastResult(res.summary);
      notifySuccess("Cycle closed", res.summary.summarized ? "AI summary generated — pending HRBP release." : "Summary held / pending — see status.");
    } catch (err) {
      notifyError(err);
    }
  }

  async function resummarize() {
    setNoProvider(false);
    try {
      const res = await m.summarize.mutateAsync(cycle.id);
      setLastResult(res);
      notifySuccess("Summary regenerated");
    } catch (err) {
      if (mapApiError(err).kind === "ai_unavailable") setNoProvider(true);
      else notifyError(err);
    }
  }

  return (
    <div className="space-y-6">
      {/* Lifecycle action */}
      <section className="space-y-2">
        {isDraft && (
          <Button onClick={() => m.openCycle.mutateAsync(cycle.id).then(() => notifySuccess("Cycle opened")).catch(notifyError)} loading={m.openCycle.isPending}>
            <Send className="h-4 w-4" /> Open for collection
          </Button>
        )}
        {isCollecting && (
          <Button onClick={close} loading={m.closeCycle.isPending}>
            <Sparkles className="h-4 w-4" /> Close &amp; summarize (Agent 3)
          </Button>
        )}
        {isClosed && (
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={resummarize} loading={m.summarize.isPending}>
              <Sparkles className="h-4 w-4 text-ai" /> Re-summarize
            </Button>
            <span className="text-2xs text-muted-foreground">Released summaries live in “Summaries to release”.</span>
          </div>
        )}
        {lastResult && (
          <Alert variant={lastResult.summarized ? "ai" : "warning"}>
            <ShieldCheck />
            <AlertTitle>
              {lastResult.summarized ? "Summary generated → pending HRBP release" : lastResult.reason === "anonymity_breach" ? "Held: possible anonymity breach" : `Held / ${humanize(lastResult.status ?? "pending")}`}
            </AlertTitle>
            <AlertDescription>
              {lastResult.reason === "anonymity_breach"
                ? "The generated text was held HRBP_HOLD for human judgement — never auto-released."
                : "An HRBP must review and release it before the subject can see it."}
            </AlertDescription>
          </Alert>
        )}
        {noProvider && (
          <Alert variant="ai">
            <Sparkles />
            <AlertTitle>AI summary not configured</AlertTitle>
            <AlertDescription>The Feedback Summarizer (Agent 3) isn't connected for this tenant.</AlertDescription>
          </Alert>
        )}
      </section>

      {/* Invitations */}
      <section className="space-y-2 border-t border-border pt-5">
        <h4 className="text-sm font-semibold">Reviewers</h4>
        {invitations.isLoading ? (
          <LinesSkeleton lines={3} />
        ) : invitations.data && invitations.data.length > 0 ? (
          <ul className="space-y-1.5">
            {invitations.data.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2">
                <span className="flex items-center gap-2 text-sm">
                  <PersonName id={r.giver} />
                  <Badge variant="muted">{humanize(r.relationship)}</Badge>
                </span>
                <StatusBadge status={r.status} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">No reviewers invited yet.</p>
        )}
        {isCollecting && <InviteForm cycleId={cycle.id} mutation={m.invite} />}
      </section>

      {/* Anonymized payload (closed) */}
      {isClosed && (
        <section className="space-y-2 border-t border-border pt-5">
          <h4 className="flex items-center gap-1.5 text-sm font-semibold"><Lock className="h-3.5 w-3.5" /> Anonymised responses</h4>
          {anonymized.isLoading ? (
            <LinesSkeleton lines={3} />
          ) : anonymized.isError ? (
            <p className="text-sm text-muted-foreground">{mapApiError(anonymized.error).message}</p>
          ) : anonymized.data ? (
            <AnonymizedView payload={anonymized.data} />
          ) : null}
        </section>
      )}
    </div>
  );
}

function AnonymizedView({ payload }: { payload: import("@/lib/types").AnonymizedPayload }) {
  const groups = Object.entries(payload.groups);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5 text-2xs">
        {(["SELF", "MANAGER", "PEER", "UPWARD"] as const).map((g) => {
          const n = payload.volumes[g] ?? 0;
          const suppressed = payload.insufficient_groups.includes(g);
          return (
            <Badge key={g} variant={suppressed ? "muted" : "secondary"}>
              {humanize(g)}: {n}{suppressed ? " (suppressed <min)" : ""}
            </Badge>
          );
        })}
      </div>
      {groups.length === 0 ? (
        <p className="text-sm text-muted-foreground">No group reached the minimum volume — nothing is egressed.</p>
      ) : (
        groups.map(([group, items]) => (
          <div key={group}>
            <p className="mb-1 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">{humanize(group)}</p>
            <ul className="space-y-1">
              {(items ?? []).map((it) => (
                <li key={it.pseudonym} className="rounded-md bg-secondary/50 px-3 py-1.5 text-sm">
                  <span className="mr-2 font-mono text-2xs text-muted-foreground">{it.pseudonym}</span>
                  {it.body}
                </li>
              ))}
            </ul>
          </div>
        ))
      )}
      <p className="text-2xs text-muted-foreground">Giver identities are never egressed — only opaque pseudonyms.</p>
    </div>
  );
}

function InviteForm({ cycleId, mutation }: { cycleId: string; mutation: ReturnType<typeof useFeedbackMutations>["invite"] }) {
  const { nodes } = useDirectory();
  const [giver, setGiver] = React.useState("");
  const [relationship, setRelationship] = React.useState("PEER");

  return (
    <div className="grid grid-cols-12 items-end gap-2 border-t border-border pt-3">
      <Field label="Invite reviewer" className="col-span-6">
        <Select value={giver} onValueChange={setGiver}>
          <SelectTrigger><SelectValue placeholder="Person…" /></SelectTrigger>
          <SelectContent>
            {Object.values(nodes).map((p) => (
              <SelectItem key={p.id} value={p.id}>{p.display}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <Field label="As" className="col-span-4">
        <Select value={relationship} onValueChange={setRelationship}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            {FEEDBACK_RELATIONSHIP.map((r) => (
              <SelectItem key={r} value={r}>{humanize(r)}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <div className="col-span-2">
        <Button
          variant="outline"
          className="w-full"
          disabled={!giver}
          loading={mutation.isPending}
          onClick={() =>
            mutation
              .mutateAsync({ cycleId, giver, relationship })
              .then(() => { setGiver(""); notifySuccess("Reviewer invited"); })
              .catch(notifyError)
          }
        >
          <UserPlus className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
