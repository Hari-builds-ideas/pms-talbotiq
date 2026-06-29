import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ArrowUpRight, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { aiApi } from "@/lib/api/endpoints";
import { mapApiError } from "@/lib/errors";
import type { ChatProposal } from "@/lib/types";

/**
 * The inline confirm card for a proposed assistant action (RW_BUILD_4 / AGENTIC_CHAT).
 * The proposal is INERT until the human acts. Two feels:
 *   - "confirm"  → [Approve] calls the execute endpoint (server re-checks permission +
 *     scope and audits each effect — the ONLY write path);
 *   - "navigate" → [Open …] deep-links the right screen (with prefill in the query) and
 *     the human completes + submits there via that screen's own audited endpoint — the
 *     chat never writes for these.
 *   - "clarify"  → the question is already the chat bubble text; render nothing extra.
 *
 * Action-aware: noun / success line / which query to invalidate are keyed off
 * `proposal.action`; an unknown action falls back to a generic message.
 */
// Per action: the success noun + which query PREFIXES to invalidate so the open screen
// refetches immediately (the prefix pattern from BUG 1). Every confirm action MUST list
// its prefixes — a missing entry was why chat-initiated 360 / enrich / draft didn't
// update live until reload.
const ACTION_META: Record<string, { noun: string; invalidate: string[] }> = {
  approve_goals: { noun: "goal", invalidate: ["goals", "cycles"] },
  approve_reviews: { noun: "review", invalidate: ["reviews"] },
  draft_review: { noun: "review", invalidate: ["reviews"] },
  initiate_360: { noun: "360 cycle", invalidate: ["feedback"] },
  career_enrich: { noun: "roadmap", invalidate: ["career"] },
  succession_enrich: { noun: "plan", invalidate: ["succession"] },
};

function prefillQuery(prefill?: Record<string, unknown>): string {
  if (!prefill) return "";
  const entries = Object.entries(prefill)
    .filter(([, v]) => v !== undefined && v !== null && String(v) !== "")
    .map(([k, v]) => [k, String(v)] as [string, string]);
  if (!entries.length) return "";
  return "?" + new URLSearchParams(entries).toString();
}

export function ProposalCard({ proposal }: { proposal: ChatProposal }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [phase, setPhase] = React.useState<"pending" | "running" | "done" | "cancelled">("pending");
  const [result, setResult] = React.useState("");

  const feel = proposal.feel ?? "confirm";

  // "clarify" — the summary (already shown as the bubble text) IS the prompt; nothing to render.
  if (feel === "clarify") return null;

  // "navigate" — deep-link the screen; the human completes it there (no chat write).
  if (feel === "navigate") {
    if (phase === "cancelled") {
      return <p className="mt-1 text-2xs italic opacity-80">Dismissed.</p>;
    }
    return (
      <div className="mt-1.5 flex gap-2">
        <Button
          size="sm"
          onClick={() => proposal.deeplink && navigate(proposal.deeplink + prefillQuery(proposal.prefill))}
        >
          <ArrowUpRight className="h-3.5 w-3.5" /> Open the screen
        </Button>
        <Button size="sm" variant="outline" onClick={() => setPhase("cancelled")}>Dismiss</Button>
      </div>
    );
  }

  // "confirm" — Approve → execute (the only write path).
  const meta = ACTION_META[proposal.action] ?? { noun: "item", invalidate: [] as string[] };

  async function approve() {
    setPhase("running");
    try {
      const r = await aiApi.executeAction(proposal.action, proposal.params ?? {});
      // Refetch every affected screen immediately (prefix invalidation — BUG 1 pattern).
      meta.invalidate.forEach((k) => void qc.invalidateQueries({ queryKey: [k] }));
      if (r.message) {
        setResult(r.message); // AGENTIC_CHAT confirm actions report their own line
      } else {
        const n = r.approved ?? 0;
        const skipped = r.skipped?.length ?? 0;
        setResult(`Approved ${n} ${meta.noun}${n === 1 ? "" : "s"}${skipped ? `, skipped ${skipped}` : ""}.`);
      }
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
      {proposal.preview.length > 0 && (
        <ul className="mb-2 list-disc space-y-0.5 pl-4">
          {proposal.preview.slice(0, 8).map((p, i) => (
            <li key={i}>
              {p.goal ? (
                <>
                  {String(p.goal)}
                  {p.employee ? <span className="opacity-70"> · {String(p.employee)}</span> : null}
                </>
              ) : (
                String(p.employee ?? p.role ?? p.title ?? "—")
              )}
            </li>
          ))}
          {proposal.preview.length > 8 && (
            <li className="opacity-70">…and {proposal.preview.length - 8} more</li>
          )}
        </ul>
      )}
      <div className="flex gap-2">
        <Button size="sm" onClick={approve} loading={phase === "running"}>Approve</Button>
        <Button size="sm" variant="outline" onClick={() => setPhase("cancelled")}>Cancel</Button>
      </div>
    </div>
  );
}
