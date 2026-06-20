import * as React from "react";
import { Lock, Send, Sparkles, UserPlus } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
import { useQueryClient } from "@tanstack/react-query";
import { useAnonymized, useFeedbackMutations, useInvitations } from "./useFeedback";
import { useDirectory } from "@/lib/hooks/useDirectory";
import { useAIAction } from "@/lib/hooks/useAIAction";
import { AIJobBanner } from "@/components/AIJobBanner";
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
            {cycle && <>360 for <PersonName id={cycle.subject} name={cycle.subject_name} /></>}
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
  const qc = useQueryClient();
  const invitations = useInvitations(cycle.id);
  const anonymized = useAnonymized(cycle.id, cycle.status === "CLOSED");

  const isDraft = cycle.status === "DRAFT";
  const isCollecting = cycle.status === "COLLECTING";
  const isClosed = cycle.status === "CLOSED";

  // Close is synchronous (the cycle freezes immediately); the Agent-3 summary it
  // fires is async. Re-summarize is fully async. Both poll the AI job: the banner
  // shows working / held-for-anonymity (DEGRADED) / unavailable; SUCCEEDED toasts.
  const closeAi = useAIAction(
    () =>
      m.closeCycle.mutateAsync(cycle.id).then((r) => {
        void qc.invalidateQueries({ queryKey: ["feedback"] }); // cycle is now CLOSED
        return r.job;
      }),
    {
      onSucceeded: () => {
        void qc.invalidateQueries({ queryKey: ["feedback"] });
        notifySuccess("Summary generated", "Pending HRBP release.");
      },
    },
  );
  const resummarizeAi = useAIAction(() => m.summarize.mutateAsync(cycle.id), {
    onSucceeded: () => {
      void qc.invalidateQueries({ queryKey: ["feedback"] });
      notifySuccess("Summary regenerated", "Pending HRBP release.");
    },
  });

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
          <Button onClick={closeAi.start} loading={closeAi.isWorking}>
            <Sparkles className="h-4 w-4" /> Close &amp; summarize (Agent 3)
          </Button>
        )}
        {isClosed && (
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={resummarizeAi.start} loading={resummarizeAi.isWorking}>
              <Sparkles className="h-4 w-4 text-ai" /> Re-summarize
            </Button>
            <span className="text-2xs text-muted-foreground">Released summaries live in “Summaries to release”.</span>
          </div>
        )}
        <AIJobBanner job={closeAi.job} working="Closing & summarizing…" />
        <AIJobBanner job={resummarizeAi.job} working="Re-summarizing…" onRetry={resummarizeAi.start} />
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
                  <PersonName id={r.giver} name={r.giver_name} />
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
