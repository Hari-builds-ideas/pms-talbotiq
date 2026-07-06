import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  ArrowUpRight,
  Award,
  Check,
  ChevronDown,
  Circle,
  ClipboardList,
  FileText,
  GitBranch,
  Loader2,
  MessageSquare,
  PlayCircle,
  SkipForward,
  Sparkles,
  Target,
  UserCheck,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { aiApi } from "@/lib/api/endpoints";
import { useAIJob } from "@/lib/hooks/useAIJob";
import { mapApiError } from "@/lib/errors";
import { cn } from "@/lib/utils";
import type { ChatPlan, ChatPlanStep } from "@/lib/types";

/**
 * The AGENT plan surface (AGENT_UX_V3 §B–E). A plan is an ORDERED, INERT checklist —
 * the human approves one step at a time OR "Approve all & run" (frontend-only
 * sequential orchestration over the SAME per-step approve endpoint). Each executed
 * step re-checks capability + scope server-side and returns a rich ARTIFACT (result
 * card + Open → deep link); async drafts are tracked live via the shared job poll.
 * Nothing runs on render, and a failed step STOPS the run (the rest stay pending).
 */
const INVALIDATE: Record<string, string[]> = {
  approve_goal: ["goals", "cycles"],
  approve_goals: ["goals", "cycles"],
  approve_reviews: ["reviews"],
  draft_review: ["reviews"],
  schedule_review: ["reviews"],
  initiate_360: ["feedback"],
  career_enrich: ["career"],
  succession_enrich: ["succession"],
  record_actual: ["goals"],
  update_kpi_actual: ["goals"],
  give_recognition: ["recognition"],
  open_checkin: ["checkins"],
  respond_to_checkin: ["checkins"],
};

const ACTION_LABEL: Record<string, string> = {
  approve_goal: "Approve goal",
  approve_goals: "Approve goals",
  approve_reviews: "Approve reviews",
  draft_review: "Draft review",
  schedule_review: "Schedule review",
  initiate_360: "Start 360",
  career_enrich: "Enrich roadmap",
  succession_enrich: "Enrich succession plan",
  create_jd: "Create JD",
  record_actual: "Record KPI actual",
  update_kpi_actual: "Update KPI actual",
  give_recognition: "Give recognition",
  open_checkin: "Start check-in",
  respond_to_checkin: "Respond to check-in",
  clarify: "Needs a detail",
};

/** One suggested NEXT action per action (E) — prefills the input, never auto-sends. */
const SUGGEST_NEXT: Record<string, string> = {
  initiate_360: "Invite reviewers for the 360 cycle",
  draft_review: "Open the draft to review it",
  give_recognition: "Recognise someone else on the team",
  approve_goal: "Approve another pending goal",
};

const ARTIFACT_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  feedback_cycle: MessageSquare,
  review: FileText,
  recognition: Award,
  kpi: Target,
  goal: Target,
  checkin: ClipboardList,
  career_roadmap: GitBranch,
  succession_plan: GitBranch,
};

type StepStatus = ChatPlanStep["status"];

interface Artifact {
  type: string;
  id: string | null;
  title: string;
  state: string;
  deeplink: string;
}
interface StepResult {
  artifact?: Artifact;
  jobId?: string;
  message?: string;
}

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

/** A rich result card for an executed step's artifact, with a primary Open → link. */
function ResultCard({ artifact }: { artifact: Artifact }) {
  const navigate = useNavigate();
  const Icon = ARTIFACT_ICON[artifact.type] ?? UserCheck;
  return (
    <div className="mt-1.5 ml-7 flex items-center gap-2 rounded-md border border-success/30 bg-success-subtle/40 p-2">
      <Icon className="h-4 w-4 shrink-0 text-success" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-2xs font-medium text-foreground">{artifact.title}</p>
        <p className="text-2xs text-muted-foreground">{artifact.state}</p>
      </div>
      {artifact.deeplink && (
        <Button size="sm" variant="outline" onClick={() => navigate(artifact.deeplink)}>
          Open <ArrowUpRight className="h-3.5 w-3.5" />
        </Button>
      )}
    </div>
  );
}

/** Live async-job tracking for a draft/enrich step (C) — reuses the shared poll. */
function JobStatus({ jobId }: { jobId: string }) {
  const { data: job } = useAIJob(jobId);
  const status = job?.status;
  if (!status || status === "QUEUED" || status === "RUNNING") {
    return (
      <p className="mt-1 ml-7 flex items-center gap-1 text-2xs text-ai">
        <Loader2 className="h-3 w-3 animate-spin" /> Drafting with AI… ~20s
      </p>
    );
  }
  if (status === "SUCCEEDED") {
    return (
      <p className="mt-1 ml-7 flex items-center gap-1 text-2xs text-success">
        <Check className="h-3 w-3" /> Draft ready — pending your review.
      </p>
    );
  }
  // DEGRADED / FAILED — honest, never fake success.
  return (
    <p className="mt-1 ml-7 flex items-center gap-1 text-2xs text-warning">
      <X className="h-3 w-3" /> AI unavailable — nothing was changed.
    </p>
  );
}

export function PlanChecklist({
  plan,
  onSuggest,
}: {
  plan: ChatPlan;
  onSuggest?: (text: string) => void;
}) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [statuses, setStatuses] = React.useState<Record<string, StepStatus>>(
    () => Object.fromEntries(plan.steps.map((s) => [s.id, s.status])),
  );
  const [results, setResults] = React.useState<Record<string, StepResult>>({});
  const [notes, setNotes] = React.useState<Record<string, string>>({});
  const [expanded, setExpanded] = React.useState<Record<string, boolean>>({});
  const [busy, setBusy] = React.useState<string | null>(null);
  const [running, setRunning] = React.useState(false);

  if (plan.steps.length === 0) {
    return <p className="mt-1 text-2xs italic opacity-80">{plan.summary || "Nothing to do."}</p>;
  }

  // Execute ONE step through the existing gate. Returns true on success (so run-all
  // can sequence + stop on the first failure / clarify).
  async function approve(step: ChatPlanStep): Promise<boolean> {
    if (statuses[step.id] && statuses[step.id] !== "pending") return true;
    if (step.feel === "clarify") return false; // pauses a run — needs the picker
    if (step.feel === "navigate") {
      if (step.deeplink) navigate(step.deeplink + prefillQuery(step.prefill));
      setStatuses((s) => ({ ...s, [step.id]: "done" }));
      return true;
    }
    setBusy(step.id);
    setStatuses((s) => ({ ...s, [step.id]: "approved" }));
    try {
      const r = await aiApi.approveStep(plan.id, step.id);
      const st: StepStatus =
        r.status === "in_progress" ? "done" : r.status === "needs_clarification" ? "pending" : r.status;
      setStatuses((s) => ({ ...s, [step.id]: st }));
      const res = (r.result ?? {}) as Record<string, unknown>;
      setResults((m) => ({
        ...m,
        [step.id]: {
          artifact: res.artifact as Artifact | undefined,
          jobId: res.job_id as string | undefined,
          message: res.message as string | undefined,
        },
      }));
      const msg =
        r.status === "needs_clarification"
          ? r.question || "I need one more detail."
          : (res.message as string) || (r.out_of_order ? "Done (out of order)." : "Done.");
      setNotes((n) => ({ ...n, [step.id]: msg }));
      (INVALIDATE[step.action] ?? []).forEach((k) => void qc.invalidateQueries({ queryKey: [k] }));
      return st === "done";
    } catch (err) {
      setStatuses((s) => ({ ...s, [step.id]: "failed" }));
      setNotes((n) => ({ ...n, [step.id]: mapApiError(err).message }));
      return false;
    } finally {
      setBusy(null);
    }
  }

  // Approve all & run (D) — sequential over the SAME endpoint; stop on failure/clarify.
  async function runAll() {
    setRunning(true);
    try {
      for (const step of plan.steps) {
        if (statuses[step.id] && statuses[step.id] !== "pending") continue;
        if (step.feel === "clarify") break; // pause: reply above to continue
        const ok = await approve(step);
        if (!ok) break; // a failed step stops the run; the rest stay pending
      }
    } finally {
      setRunning(false);
    }
  }

  const settled = plan.steps.every((s) => {
    const st = statuses[s.id] ?? "pending";
    return st === "done" || st === "skipped" || st === "failed";
  });
  const doneCount = plan.steps.filter((s) => statuses[s.id] === "done").length;
  const anyPendingConfirmOrNav = plan.steps.some(
    (s) => (statuses[s.id] ?? "pending") === "pending" && s.feel !== "clarify",
  );
  // A suggestion for the first executed step that maps to a next action.
  const suggestSource = plan.steps.find((s) => statuses[s.id] === "done" && SUGGEST_NEXT[s.action]);
  const suggestion = suggestSource ? SUGGEST_NEXT[suggestSource.action] : null;

  return (
    <div className="mt-1.5 space-y-1.5 rounded-md border border-ai/30 bg-card/60 p-2 text-xs">
      {plan.steps.length > 1 && anyPendingConfirmOrNav && (
        <div className="flex justify-end">
          <Button size="sm" onClick={runAll} loading={running} disabled={running || Boolean(busy)}>
            <PlayCircle className="h-3.5 w-3.5" /> Approve all &amp; run
          </Button>
        </div>
      )}
      {plan.steps.map((step, i) => {
        const status = statuses[step.id] ?? "pending";
        const pending = status === "pending";
        const res = results[step.id];
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
            {res?.artifact && <ResultCard artifact={res.artifact} />}
            {res?.jobId && <JobStatus jobId={res.jobId} />}
            {notes[step.id] && !res?.artifact && (
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
                <Button size="sm" onClick={() => approve(step)} loading={busy === step.id} disabled={running}>
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
                  disabled={running}
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

      {/* Completion summary (E) — N of N done + one suggested next step. */}
      {settled && doneCount > 0 && (
        <div className="mt-1 rounded border border-success/30 bg-success-subtle/30 p-2">
          <p className="flex items-center gap-1 font-medium text-foreground">
            <Check className="h-3.5 w-3.5 text-success" />
            {doneCount} of {plan.steps.length} done.
          </p>
          {suggestion && onSuggest && (
            <button
              type="button"
              onClick={() => onSuggest(suggestion)}
              className="mt-1.5 inline-flex items-center gap-1 rounded-full border border-ai/40 bg-ai-subtle px-2.5 py-1 text-2xs font-medium text-ai hover:bg-ai/10"
            >
              <Sparkles className="h-3 w-3" /> {suggestion}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
