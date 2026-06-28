import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { aiApi } from "@/lib/api/endpoints";
import { mapApiError } from "@/lib/errors";
import type { ChatProposal } from "@/lib/types";

/**
 * The inline confirm card for a proposed assistant action (RW_BUILD_4/5). The
 * proposal is INERT — nothing happens until the human taps Approve, which calls the
 * execute endpoint (the server re-checks permission + scope and audits each effect).
 *
 * Action-aware: the registry can propose more than one action (approve_goals,
 * approve_reviews). The noun, the success line, and which query to invalidate are all
 * keyed off `proposal.action`, so a new action type slots in with one map entry.
 */
const ACTION_META: Record<string, { noun: string; invalidate: string }> = {
  approve_goals: { noun: "goal", invalidate: "goals" },
  approve_reviews: { noun: "review", invalidate: "reviews" },
};

export function ProposalCard({ proposal }: { proposal: ChatProposal }) {
  const qc = useQueryClient();
  const [phase, setPhase] = React.useState<"pending" | "running" | "done" | "cancelled">("pending");
  const [result, setResult] = React.useState("");

  const meta = ACTION_META[proposal.action] ?? { noun: "item", invalidate: "" };

  async function approve() {
    setPhase("running");
    try {
      const r = await aiApi.executeAction(proposal.action, proposal.params);
      // Refresh the affected list so an open screen reflects the approvals.
      if (meta.invalidate) void qc.invalidateQueries({ queryKey: [meta.invalidate] });
      const n = r.approved ?? 0;
      const skipped = r.skipped?.length ?? 0;
      setResult(
        `Approved ${n} ${meta.noun}${n === 1 ? "" : "s"}${skipped ? `, skipped ${skipped}` : ""}.`,
      );
      setPhase("done");
    } catch (err) {
      setResult(mapApiError(err).message);
      setPhase("done");
    }
  }

  if (phase === "cancelled") {
    return <p className="mt-1 text-2xs italic opacity-80">Cancelled — nothing was changed.</p>;
  }
  if (phase === "done") {
    return (
      <p className="mt-1 flex items-center gap-1 text-2xs">
        <Check className="h-3 w-3 text-success" /> {result}
      </p>
    );
  }
  return (
    <div className="mt-1.5 rounded-md border border-ai/30 bg-card/60 p-2 text-xs text-foreground">
      <ul className="mb-2 list-disc space-y-0.5 pl-4">
        {proposal.preview.slice(0, 8).map((p, i) => (
          <li key={i}>
            {p.goal ? (
              <>
                {String(p.goal)}
                {p.employee ? <span className="opacity-70"> · {String(p.employee)}</span> : null}
              </>
            ) : (
              String(p.employee ?? "—")
            )}
          </li>
        ))}
        {proposal.preview.length > 8 && (
          <li className="opacity-70">…and {proposal.preview.length - 8} more</li>
        )}
      </ul>
      <div className="flex gap-2">
        <Button size="sm" onClick={approve} loading={phase === "running"}>Approve</Button>
        <Button size="sm" variant="outline" onClick={() => setPhase("cancelled")}>Cancel</Button>
      </div>
    </div>
  );
}
