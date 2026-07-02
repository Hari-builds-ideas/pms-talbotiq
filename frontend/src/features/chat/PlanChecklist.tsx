import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ArrowUpRight, Check, ChevronDown, Circle, SkipForward, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { aiApi } from "@/lib/api/endpoints";
import { mapApiError } from "@/lib/errors";
import { cn } from "@/lib/utils";
import type { ChatPlan, ChatPlanStep } from "@/lib/types";

/**
 * The AGENT plan surface (OVERNIGHT_A). A plan is an ORDERED, INERT checklist — the
 * human approves one step at a time; each approve calls the server, which re-checks
 * capability + scope and audits (the only write path). Nothing runs on render.
 *
 * Per step: a grounded reason (Explain), and Approve · Skip · (Open for navigate).
 * A single-action request shows a 1-step plan — same discipline, richer surface.
 */
const INVALIDATE: Record<string, string[]> = {
  approve_goals: ["goals", "cycles"],
  approve_reviews: ["reviews"],
  draft_review: ["reviews"],
  initiate_360: ["feedback"],
  career_enrich: ["career"],
  succession_enrich: ["succession"],
  record_actual: ["goals"],
  give_recognition: ["recognition"],
};

const ACTION_LABEL: Record<string, string> = {
  approve_goals: "Approve goals",
  approve_reviews: "Approve reviews",
  draft_review: "Draft review",
  initiate_360: "Start 360",
  career_enrich: "Enrich roadmap",
  succession_enrich: "Enrich succession plan",
  create_jd: "Create JD",
  record_actual: "Record KPI actual",
  give_recognition: "Give recognition",
  clarify: "Needs a detail",
};

type StepStatus = ChatPlanStep["status"];

function prefillQuery(prefill?: Record<string, unknown>): string {
  if (!prefill) return "";
  const entries = Object.entries(prefill)
    .filter(([, v]) => v !== undefined && v !== null && String(v) !== "")
    .map(([k, v]) => [k, String(v)] as [string, string]);
  return entries.length ? "?" + new URLSearchParams(entries).toString() : "";
}

function StatusBadge({ status }: { status: StepStatus }) {
  if (status === "done") return <Badge variant="success">Done</Badge>;
  if (status === "failed") return <Badge variant="danger">Failed</Badge>;
  if (status === "skipped") return <Badge variant="outline">Skipped</Badge>;
  if (status === "approved") return <Badge variant="secondary">Running…</Badge>;
  return <Badge variant="outline">Pending</Badge>;
}

export function PlanChecklist({ plan }: { plan: ChatPlan }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [statuses, setStatuses] = React.useState<Record<string, StepStatus>>(
    () => Object.fromEntries(plan.steps.map((s) => [s.id, s.status])),
  );
  const [notes, setNotes] = React.useState<Record<string, string>>({});
  const [expanded, setExpanded] = React.useState<Record<string, boolean>>({});
  const [busy, setBusy] = React.useState<string | null>(null);

  if (plan.steps.length === 0) {
    return <p className="mt-1 text-2xs italic opacity-80">{plan.summary || "Nothing to do."}</p>;
  }

  async function approve(step: ChatPlanStep) {
    if (step.feel === "navigate") {
      if (step.deeplink) navigate(step.deeplink + prefillQuery(step.prefill));
      setStatuses((s) => ({ ...s, [step.id]: "done" }));
      return;
    }
    setBusy(step.id);
    setStatuses((s) => ({ ...s, [step.id]: "approved" }));
    try {
      const r = await aiApi.approveStep(plan.id, step.id);
      const st: StepStatus =
        r.status === "in_progress" ? "done" : r.status === "needs_clarification" ? "pending" : r.status;
      setStatuses((s) => ({ ...s, [step.id]: st }));
      const msg =
        r.status === "needs_clarification"
          ? r.question || "I need one more detail."
          : (r.result?.message as string) || (r.out_of_order ? "Done (out of order)." : "Done.");
      setNotes((n) => ({ ...n, [step.id]: msg }));
      (INVALIDATE[step.action] ?? []).forEach((k) => void qc.invalidateQueries({ queryKey: [k] }));
    } catch (err) {
      setStatuses((s) => ({ ...s, [step.id]: "failed" }));
      setNotes((n) => ({ ...n, [step.id]: mapApiError(err).message }));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mt-1.5 space-y-1.5 rounded-md border border-ai/30 bg-card/60 p-2 text-xs">
      {plan.steps.map((step, i) => {
        const status = statuses[step.id] ?? "pending";
        const pending = status === "pending";
        return (
          <div key={step.id} className="rounded border border-border/60 bg-background/40 p-2">
            <div className="flex items-center gap-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-ai-subtle text-2xs font-semibold text-ai">
                {i + 1}
              </span>
              <span className="flex-1 font-medium text-foreground">
                {ACTION_LABEL[step.action] ?? step.action}
              </span>
              <StatusBadge status={status} />
            </div>
            <p className="mt-1 pl-7 text-foreground/90">{step.summary}</p>
            {step.reason && (
              <button
                type="button"
                onClick={() => setExpanded((e) => ({ ...e, [step.id]: !e[step.id] }))}
                className="mt-1 flex items-center gap-1 pl-7 text-2xs text-muted-foreground hover:text-foreground"
              >
                <ChevronDown className={cn("h-3 w-3 transition", expanded[step.id] && "rotate-180")} />
                Explain
              </button>
            )}
            {expanded[step.id] && step.reason && (
              <p className="mt-1 pl-7 text-2xs italic text-muted-foreground">{step.reason}</p>
            )}
            {notes[step.id] && (
              <p className="mt-1 flex items-center gap-1 pl-7 text-2xs">
                {status === "failed" ? (
                  <X className="h-3 w-3 text-destructive" />
                ) : (
                  <Check className="h-3 w-3 text-success" />
                )}
                {notes[step.id]}
              </p>
            )}
            {pending && step.feel !== "clarify" && (
              <div className="mt-1.5 flex gap-2 pl-7">
                <Button size="sm" onClick={() => approve(step)} loading={busy === step.id}>
                  {step.feel === "navigate" ? (
                    <>
                      <ArrowUpRight className="h-3.5 w-3.5" /> Open the screen
                    </>
                  ) : (
                    <>
                      <Check className="h-3.5 w-3.5" /> Approve
                    </>
                  )}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setStatuses((s) => ({ ...s, [step.id]: "skipped" }))}
                >
                  <SkipForward className="h-3.5 w-3.5" /> Skip
                </Button>
              </div>
            )}
            {pending && step.feel === "clarify" && (
              <p className="mt-1 flex items-center gap-1 pl-7 text-2xs text-muted-foreground">
                <Circle className="h-3 w-3" /> Reply above to continue.
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
